"""As quatro Ações como tools do LangChain, criadas a cada passo com o Cliente e a Conversa
fixos. O modelo só escolhe a Ação e os argumentos; quem executa, e quem confere se o Pedido é
mesmo do Cliente, é o código daqui.

As tools não guardam estado: o nó `agente` descobre o que rodou pelas ToolMessages. Cada
Ação é anunciada no stream como `tool_call`, para o chat mostrar o que está acontecendo.

`emitir_reembolso` não decide nada sozinho. A decisão do Gate de Aprovação já foi tomada pelo
nó e gravada no estado antes de a tool rodar. Se ela exige um Atendente, a tool chama
`interrupt` e a Conversa vira Aprovação Pendente; na retomada, a tool roda de novo com a mesma
decisão gravada e `interrupt` devolve a resposta do Atendente.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool, tool
from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from ampere.acoes.reembolso import DecisaoGravada, motivo_para_recusar
from ampere.acoes.ticket import StoreDeTickets, abrir_ticket
from ampere.loja.pedidos import Pedido, Reembolso, StoreDePedidos, formatar_reais
from ampere.rag.busca import Retriever, formatar_chunks

NOMES_DAS_ACOES = (
    "consultar_pedido",
    "consultar_base_de_conhecimento",
    "emitir_reembolso",
    "abrir_ticket",
)


@dataclass(frozen=True)
class ContextoDoTurno:
    """O que as Ações precisam saber sobre o turno em andamento."""

    cliente_id: str
    conversa_id: str
    messages: list[BaseMessage]
    decisoes_do_gate: Mapping[str, DecisaoGravada]


def anunciar(nome: str, args: dict[str, Any]) -> None:
    """Registra a Ação no stream (evento `tool_call`); fora de um grafo, não faz nada."""
    try:
        escrever = get_stream_writer()
    except RuntimeError:
        return
    escrever({"tipo": "tool_call", "nome": nome, "args": args})


def criar_tools(
    turno: ContextoDoTurno,
    *,
    pedidos: StoreDePedidos,
    tickets: StoreDeTickets,
    retriever: Retriever,
    trabalhador: BaseChatModel,
) -> list[BaseTool]:
    def pedido_do_cliente(pedido_id: str) -> Pedido | None:
        return pedidos.obter(turno.cliente_id, pedido_id)

    @tool
    def consultar_pedido(pedido_id: str) -> str:
        """Consulta o status, o produto e o valor de um Pedido do Cliente atual pelo número."""
        anunciar("consultar_pedido", {"pedido_id": pedido_id})
        pedido = pedido_do_cliente(pedido_id)
        return pedido.resumo() if pedido else _nao_encontrado(pedido_id)

    @tool
    def consultar_base_de_conhecimento(pergunta: str) -> str:
        """Busca nas políticas da Loja (troca, devolução, frete, garantia, pagamento, cadastro)."""
        anunciar("consultar_base_de_conhecimento", {"pergunta": pergunta})
        chunks = retriever.buscar(pergunta, k=5)
        return formatar_chunks(chunks) if chunks else "Nenhuma política encontrada."

    @tool
    def emitir_reembolso(pedido_id: str, motivo: str) -> str:
        """Emite o Reembolso de um Pedido do Cliente. Pode exigir aprovação de um Atendente."""
        anunciar("emitir_reembolso", {"pedido_id": pedido_id, "motivo": motivo})
        pedido = pedido_do_cliente(pedido_id)
        if pedido is None:
            return _nao_encontrado(pedido_id)
        recusa = motivo_para_recusar(pedido, pedidos)
        if recusa:
            return f"Não é possível reembolsar o Pedido {pedido.id}: {recusa}."

        decisao = turno.decisoes_do_gate[pedido.id]
        aprovado_pelo_atendente = False
        if decisao["exige_aprovacao"]:
            resposta = interrupt(
                {
                    "tipo": "aprovacao",
                    "pedido_id": pedido.id,
                    "valor": float(pedido.valor),
                    "probabilidade": decisao["probabilidade"],
                    "motivo_do_gate": decisao["motivo"],
                    "resumo": f"{pedido.resumo()}. Motivo do Cliente: {motivo}",
                }
            )
            if not resposta.get("aprovado"):
                return (
                    f"Reembolso do Pedido {pedido.id} REJEITADO pelo Atendente. "
                    f"Motivo: {resposta.get('motivo') or 'não informado'}. "
                    "Explique o motivo ao Cliente."
                )
            aprovado_pelo_atendente = True

        pedidos.registrar_reembolso(
            Reembolso(pedido_id=pedido.id, cliente_id=turno.cliente_id, valor=pedido.valor)
        )
        por_quem = " (aprovado pelo Atendente)" if aprovado_pelo_atendente else ""
        valor = formatar_reais(pedido.valor)
        return f"Reembolso de {valor} do Pedido {pedido.id} registrado{por_quem}."

    @tool("abrir_ticket")
    def abrir_ticket_para_atendente(motivo: str) -> str:
        """Abre um Ticket para um Atendente humano quando não for possível resolver."""
        anunciar("abrir_ticket", {"motivo": motivo})
        ticket = abrir_ticket(
            trabalhador,
            tickets,
            conversa_id=turno.conversa_id,
            cliente_id=turno.cliente_id,
            messages=turno.messages,
        )
        return (
            f"Ticket {ticket.id} aberto (categoria {ticket.categoria}, prioridade "
            f"{ticket.prioridade}). Avise o Cliente que um Atendente vai continuar o atendimento."
        )

    return [
        consultar_pedido,
        consultar_base_de_conhecimento,
        emitir_reembolso,
        abrir_ticket_para_atendente,
    ]


def _nao_encontrado(pedido_id: str) -> str:
    return f"Pedido {pedido_id} não encontrado entre os Pedidos deste Cliente."
