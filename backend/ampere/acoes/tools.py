"""As quatro Ações como tools do LangChain, criadas por turno com o Cliente e a Conversa fixos.

Cada Ação é registrada no stream como `tool_call` (para o indicador do chat) e devolve texto
para o gerador continuar. `emitir_reembolso` passa pelo Gate de Aprovação e, quando o Gate
exige um Atendente, chama `interrupt`: a Conversa vira Aprovação Pendente até o worker
retomar o grafo com `Command(resume=...)`.
"""

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool, tool
from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from ampere.acoes.pedidos import Reembolso, StoreDePedidos
from ampere.acoes.reembolso import avaliar_gate
from ampere.acoes.ticket import StoreDeTickets, abrir_ticket
from ampere.nucleo.config import Config
from ampere.nucleo.modelos import FabricaDeModelos
from ampere.rag.busca import Retriever

NOMES_DAS_ACOES = (
    "consultar_pedido",
    "consultar_base_de_conhecimento",
    "emitir_reembolso",
    "abrir_ticket",
)


@dataclass
class ContextoDoTurno:
    """O que as Ações precisam saber e o que elas deixam registrado para o grafo."""

    cliente_id: str
    conversa_id: str
    messages: list[BaseMessage]
    acoes_tomadas: list[str] = field(default_factory=list)
    contexto: list[dict] = field(default_factory=list)
    escalada: bool = False


def anunciar(nome: str, args: dict[str, Any]) -> None:
    """Registra a Ação no stream (evento `tool_call`); fora de um grafo, não faz nada."""
    try:
        escrever = get_stream_writer()
    except RuntimeError:
        return
    escrever({"tipo": "tool_call", "nome": nome, "args": args})


def criar_tools(
    fabrica: FabricaDeModelos,
    config: Config,
    *,
    retriever: Retriever,
    pedidos: StoreDePedidos,
    tickets: StoreDeTickets,
    turno: ContextoDoTurno,
) -> list[BaseTool]:
    @tool
    def consultar_pedido(pedido_id: str) -> str:
        """Consulta o status, o produto e o valor de um Pedido do Cliente atual pelo número."""
        anunciar("consultar_pedido", {"pedido_id": pedido_id})
        turno.acoes_tomadas.append("consultar_pedido")
        pedido = pedidos.obter(turno.cliente_id, pedido_id)
        if pedido is None:
            return f"Pedido {pedido_id} não encontrado entre os Pedidos deste Cliente."
        turno.contexto.append({"texto": pedido.resumo(), "documento": "acao:consultar_pedido"})
        return pedido.resumo()

    @tool
    def consultar_base_de_conhecimento(pergunta: str) -> str:
        """Busca nas políticas da Loja (troca, devolução, frete, garantia, pagamento, cadastro)."""
        anunciar("consultar_base_de_conhecimento", {"pergunta": pergunta})
        turno.acoes_tomadas.append("consultar_base_de_conhecimento")
        chunks = retriever.buscar(pergunta, k=5)
        turno.contexto.extend(chunk.model_dump() for chunk in chunks)
        if not chunks:
            return "Nenhuma política encontrada para essa pergunta."
        return "\n\n".join(f"[{c.documento}] {c.texto}" for c in chunks)

    @tool
    def emitir_reembolso(pedido_id: str, motivo: str) -> str:
        """Emite o Reembolso de um Pedido do Cliente. Pode exigir aprovação de um Atendente."""
        anunciar("emitir_reembolso", {"pedido_id": pedido_id, "motivo": motivo})
        turno.acoes_tomadas.append("emitir_reembolso")
        pedido = pedidos.obter(turno.cliente_id, pedido_id)
        if pedido is None:
            return f"Pedido {pedido_id} não encontrado entre os Pedidos deste Cliente."
        recentes = pedidos.reembolsos_recentes(turno.cliente_id)
        decisao = avaliar_gate(
            fabrica.jev(),
            valor=pedido.valor,
            valor_limite=config.valor_limite_reembolso,
            reembolsos_recentes=len(recentes),
            limiar=config.limiar_gate_aprovacao,
        )
        if decisao.exige_aprovacao:
            resposta = interrupt(
                {
                    "tipo": "aprovacao",
                    "pedido_id": pedido.id,
                    "valor": float(pedido.valor),
                    "probabilidade": decisao.probabilidade,
                    "motivo_do_gate": decisao.motivo,
                    "resumo": f"Reembolso de R$ {pedido.valor:.2f} do {pedido.resumo()}. "
                    f"Motivo do Cliente: {motivo}",
                }
            )
            if not resposta.get("aprovado"):
                motivo_da_rejeicao = resposta.get("motivo") or "não informado"
                return (
                    f"Reembolso do Pedido {pedido.id} REJEITADO pelo Atendente. "
                    f"Motivo: {motivo_da_rejeicao}. Explique o motivo ao Cliente."
                )
        pedidos.registrar_reembolso(
            Reembolso(pedido_id=pedido.id, cliente_id=turno.cliente_id, valor=pedido.valor)
        )
        aprovacao = " (aprovado pelo Atendente)" if decisao.exige_aprovacao else ""
        return f"Reembolso de R$ {pedido.valor:.2f} do Pedido {pedido.id} registrado{aprovacao}."

    @tool
    def abrir_ticket_para_atendente(motivo: str) -> str:
        """Abre um Ticket para um Atendente humano quando não for possível resolver."""
        anunciar("abrir_ticket", {"motivo": motivo})
        turno.acoes_tomadas.append("abrir_ticket")
        ticket = abrir_ticket(
            fabrica.trabalhador(),
            tickets,
            conversa_id=turno.conversa_id,
            cliente_id=turno.cliente_id,
            messages=turno.messages,
        )
        turno.escalada = True
        return (
            f"Ticket {ticket.id} aberto (categoria {ticket.categoria}, prioridade "
            f"{ticket.prioridade}). Avise o Cliente que um Atendente vai continuar o atendimento."
        )

    abrir_ticket_para_atendente.name = "abrir_ticket"
    return [
        consultar_pedido,
        consultar_base_de_conhecimento,
        emitir_reembolso,
        abrir_ticket_para_atendente,
    ]
