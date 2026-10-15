"""Os nós do grafo, na ordem em que uma mensagem os atravessa:

    carregar_memoria → guardrail_entrada → roteador
        → recuperar_contexto → gerar_resposta    (dúvida)
        → agente ⟲                               (transação)
        → escalar                                (quer humano)
    → guardrail_saida → salvar_memoria

`escalar` também recebe a segunda reprovação do Guardrail de saída. Cada nó é um método que
lê o estado e devolve só o que muda; modelos, retriever e stores chegam pelo construtor.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.runtime import Runtime
from langgraph.types import Command

from ampere.acoes.reembolso import REGRAS as REGRAS_DO_GATE
from ampere.acoes.reembolso import DecisaoGravada, avaliar_gate, motivo_para_recusar
from ampere.acoes.ticket import RESPOSTA_AO_ABRIR_TICKET, StoreDeTickets, abrir_ticket
from ampere.acoes.tools import ContextoDoTurno, anunciar, criar_tools
from ampere.grafo.estado import EstadoDaConversa, inicio_do_turno
from ampere.guardrails.entrada import REGRAS as REGRAS_DE_ENTRADA
from ampere.guardrails.entrada import avaliar_entrada
from ampere.guardrails.mascaramento import mascarar
from ampere.guardrails.saida import REGRAS as REGRAS_DE_SAIDA
from ampere.guardrails.saida import RESPOSTA_ESCALADA, avaliar_saida
from ampere.loja.pedidos import Pedido, StoreDePedidos
from ampere.memoria.carregar import carregar_memorias
from ampere.memoria.salvar import salvar_memorias
from ampere.memoria.tipos import Memorias, memorias_vazias
from ampere.nucleo.config import Config
from ampere.nucleo.mensagens import (
    formatar_conversa,
    resultados_das_acoes,
    texto_da_ultima_do_cliente,
    ultima_do_cliente,
    ultima_resposta_do_assistente,
)
from ampere.nucleo.modelos import FabricaDeModelos
from ampere.observabilidade.langfuse import Observabilidade
from ampere.prompts import Prompt, carregar_prompt
from ampere.rag.busca import Retriever, formatar_chunks
from ampere.roteador.roteador import REGRAS as REGRAS_DO_ROTEADOR
from ampere.roteador.roteador import rotear

MAXIMO_DE_CORRECOES = 1
TURNOS_MANTIDOS_APOS_RESUMO = 2
AVISO_DE_RESPOSTA_REPROVADA = "(resposta reprovada pelo Guardrail de saída, não enviada)"


@dataclass(frozen=True)
class Dependencias:
    config: Config
    fabrica: FabricaDeModelos
    retriever: Retriever
    pedidos: StoreDePedidos
    tickets: StoreDeTickets
    observabilidade: Observabilidade


class NosDoGrafo:
    def __init__(self, deps: Dependencias) -> None:
        self.deps = deps
        self.config = deps.config
        self.obs = deps.observabilidade

    # --- 1. memória ---------------------------------------------------------------------

    def carregar_memoria(self, estado: EstadoDaConversa, runtime: Runtime) -> dict:
        mensagem = texto_da_ultima_do_cliente(estado["messages"])
        return dict(
            inicio_do_turno(carregar_memorias(runtime.store, estado["cliente_id"], mensagem))
        )

    # --- 2. Guardrail de entrada ----------------------------------------------------------

    def guardrail_entrada(self, estado: EstadoDaConversa) -> dict:
        original = ultima_do_cliente(estado["messages"])
        texto = mascarar(str(original.content))
        resultado = avaliar_entrada(
            self.deps.fabrica.jev(),
            texto,
            limiar=self.config.limiar_guardrail_entrada,
            limiar_sensivel=self.config.limiar_dado_sensivel,
            ultima_resposta=ultima_resposta_do_assistente(estado["messages"]),
        )
        self.obs.registrar_jev(
            "guardrail_entrada",
            {"mensagem": texto},
            resultado.respostas,
            metadata={
                **REGRAS_DE_ENTRADA.metadata(),
                "limiar": self.config.limiar_guardrail_entrada,
                "bloqueio": resultado.bloqueio,
            },
        )
        foi_mascarada = texto != original.content
        mensagens: list[BaseMessage] = []
        if foi_mascarada:
            mensagens.append(HumanMessage(texto, id=original.id))
        if resultado.resposta_fixa:
            mensagens.append(AIMessage(resultado.resposta_fixa))
        return {
            "mensagem_sensivel": resultado.sensivel or foi_mascarada,
            "bloqueio": resultado.bloqueio,
            **({"desfecho": "Resolvida"} if resultado.bloqueio else {}),
            **({"messages": mensagens} if mensagens else {}),
        }

    # --- 3. Roteador ----------------------------------------------------------------------

    def roteador(self, estado: EstadoDaConversa) -> dict:
        mensagem = texto_da_ultima_do_cliente(estado["messages"])
        roteamento = rotear(
            self.deps.fabrica.jev(),
            mensagem,
            episodios=estado["memorias"]["episodica"],
            ultima_resposta=ultima_resposta_do_assistente(estado["messages"]),
        )
        self.obs.registrar_jev(
            "roteador",
            {"mensagem": mensagem},
            roteamento.respostas,
            metadata={**REGRAS_DO_ROTEADOR.metadata(), "intencao": roteamento.intencao},
        )
        return {"intencao": roteamento.intencao}

    # --- 4a. caminho da dúvida -------------------------------------------------------------

    def recuperar_contexto(self, estado: EstadoDaConversa) -> dict:
        pergunta = texto_da_ultima_do_cliente(estado["messages"])
        anunciar("consultar_base_de_conhecimento", {"pergunta": pergunta})
        chunks = self.deps.retriever.buscar(pergunta, k=5)
        return {
            "contexto": [chunk.model_dump() for chunk in chunks],
            "acoes_tomadas": ["consultar_base_de_conhecimento"],
        }

    def gerar_resposta(self, estado: EstadoDaConversa) -> dict:
        prompt = carregar_prompt("gerar_resposta")
        sistema = self._prompt_de_sistema(
            prompt, estado, contexto=formatar_chunks(estado["contexto"])
        )
        resposta = self.deps.fabrica.gerador().invoke(
            [sistema, *estado["messages"]], config={"metadata": prompt.metadata()}
        )
        return {"resposta_candidata": str(resposta.content)}

    # --- 4b. caminho da transação ----------------------------------------------------------

    def agente(self, estado: EstadoDaConversa) -> Command[Literal["agente", "guardrail_saida"]]:
        """Um passo do loop: ou o modelo pede Ações, ou as Ações pedidas rodam."""
        ultima = estado["messages"][-1]
        if isinstance(ultima, AIMessage) and ultima.tool_calls:
            return self._executar_acoes(estado, ultima.tool_calls)

        prompt = carregar_prompt("agente")
        modelo = self.deps.fabrica.gerador().bind_tools(self._tools(estado))
        resposta = modelo.invoke(
            [self._prompt_de_sistema(prompt, estado), *estado["messages"]],
            config={"metadata": prompt.metadata()},
        )
        if resposta.tool_calls:
            return Command(goto="agente", update={"messages": [resposta]})
        return Command(goto="guardrail_saida", update={"resposta_candidata": str(resposta.content)})

    def _executar_acoes(
        self, estado: EstadoDaConversa, chamadas: Sequence[ToolCall]
    ) -> Command[Literal["agente"]]:
        # O Gate decide antes, num passo próprio, para a decisão ficar gravada no estado:
        # se a Ação for interrompida, a retomada lê a mesma decisão em vez de perguntar de novo.
        novas = self._decisoes_pendentes(estado, chamadas)
        if novas:
            gravadas = estado.get("decisoes_do_gate") or {}
            return Command(goto="agente", update={"decisoes_do_gate": {**gravadas, **novas}})

        tools = {tool.name: tool for tool in self._tools(estado)}
        resultados = [
            ToolMessage(
                content=str(tools[c["name"]].invoke(c["args"]))
                if c["name"] in tools
                else f"A Ação {c['name']} não existe.",
                tool_call_id=c["id"],
                name=c["name"],
            )
            for c in chamadas
        ]
        nomes = [c["name"] for c in chamadas]
        return Command(
            goto="agente",
            update={
                "messages": resultados,
                "acoes_tomadas": [*estado.get("acoes_tomadas", []), *nomes],
                **({"desfecho": "Escalada"} if "abrir_ticket" in nomes else {}),
            },
        )

    def _decisoes_pendentes(
        self, estado: EstadoDaConversa, chamadas: Sequence[ToolCall]
    ) -> dict[str, DecisaoGravada]:
        """Decisões do Gate para os Reembolsos pedidos que ainda não têm uma."""
        gravadas = estado.get("decisoes_do_gate") or {}
        novas: dict[str, DecisaoGravada] = {}
        for chamada in chamadas:
            if chamada["name"] != "emitir_reembolso":
                continue
            pedido_id = str(chamada["args"].get("pedido_id", ""))
            pedido = self.deps.pedidos.obter(estado["cliente_id"], pedido_id)
            if pedido is None or pedido.id in gravadas or pedido.id in novas:
                continue
            if motivo_para_recusar(pedido, self.deps.pedidos) is None:
                novas[pedido.id] = self._avaliar_gate(pedido)
        return novas

    def _avaliar_gate(self, pedido: Pedido) -> DecisaoGravada:
        janela = self.config.janela_reembolso_recente_dias
        decisao = avaliar_gate(
            self.deps.fabrica.jev(),
            valor=pedido.valor,
            valor_limite=self.config.valor_limite_reembolso,
            reembolsos_recentes=len(
                self.deps.pedidos.reembolsos_recentes(pedido.cliente_id, dias=janela)
            ),
            janela_dias=janela,
            limiar=self.config.limiar_gate_aprovacao,
        )
        self.obs.registrar_jev(
            "gate_de_aprovacao",
            {"pedido_id": pedido.id, "valor": float(pedido.valor)},
            decisao.respostas,
            metadata={
                **REGRAS_DO_GATE.metadata(),
                "limiar": self.config.limiar_gate_aprovacao,
                "motivo": decisao.motivo,
            },
        )
        return decisao.para_o_estado()

    def _tools(self, estado: EstadoDaConversa) -> list[BaseTool]:
        turno = ContextoDoTurno(
            cliente_id=estado["cliente_id"],
            conversa_id=estado.get("conversa_id", ""),
            messages=list(estado["messages"]),
            decisoes_do_gate=estado.get("decisoes_do_gate") or {},
        )
        return criar_tools(
            turno,
            pedidos=self.deps.pedidos,
            tickets=self.deps.tickets,
            retriever=self.deps.retriever,
            trabalhador=self.deps.fabrica.trabalhador(),
        )

    # --- 5. Guardrail de saída -------------------------------------------------------------

    def guardrail_saida(
        self, estado: EstadoDaConversa
    ) -> Command[Literal["salvar_memoria", "gerar_resposta", "agente", "escalar"]]:
        candidata = estado.get("resposta_candidata") or ""
        resultado = avaliar_saida(
            self.deps.fabrica.jev(),
            candidata,
            pergunta=texto_da_ultima_do_cliente(estado["messages"]),
            trechos=[chunk.get("texto", "") for chunk in estado.get("contexto", [])],
            resultados_das_acoes=resultados_das_acoes(estado["messages"]),
            limiar=self.config.limiar_guardrail_saida,
        )
        self.obs.registrar_jev(
            "guardrail_saida",
            {"resposta": candidata},
            resultado.respostas,
            metadata={
                **REGRAS_DE_SAIDA.metadata(),
                "limiar": self.config.limiar_guardrail_saida,
                "motivo": resultado.motivo,
            },
        )
        if resultado.aprovada:
            return Command(
                goto="salvar_memoria",
                update={
                    "messages": [AIMessage(candidata)],
                    "desfecho": estado.get("desfecho") or "Resolvida",
                },
            )
        tentativas = estado.get("tentativas", 0)
        if tentativas < MAXIMO_DE_CORRECOES:
            return Command(
                goto="gerar_resposta" if estado.get("intencao") == "duvida" else "agente",
                update={
                    "critica": resultado.critica,
                    "motivo_da_reprovacao": resultado.motivo,
                    "tentativas": tentativas + 1,
                },
            )
        return Command(
            goto="escalar",
            update={"escalada_por": "guardrail_saida", "motivo_da_reprovacao": resultado.motivo},
        )

    # --- desvio: escalar para um Atendente -------------------------------------------------

    def escalar(self, estado: EstadoDaConversa) -> dict:
        """Abre um Ticket e responde com texto fixo, sem passar pelo modelo."""
        por_guardrail = estado.get("escalada_por") == "guardrail_saida"
        conversa = list(estado["messages"])
        if por_guardrail:
            motivo = (
                f"Guardrail de saída reprovou duas vezes ({estado.get('motivo_da_reprovacao')})"
            )
            reprovada = estado.get("resposta_candidata") or ""
            conversa.append(AIMessage(f"{AVISO_DE_RESPOSTA_REPROVADA} {reprovada}"))
        else:
            motivo = "Cliente pediu para falar com uma pessoa"
        anunciar("abrir_ticket", {"motivo": motivo})
        abrir_ticket(
            self.deps.fabrica.trabalhador(),
            self.deps.tickets,
            conversa_id=estado.get("conversa_id", ""),
            cliente_id=estado["cliente_id"],
            messages=conversa,
        )
        return {
            "messages": [
                AIMessage(RESPOSTA_ESCALADA if por_guardrail else RESPOSTA_AO_ABRIR_TICKET)
            ],
            "desfecho": "Escalada",
            "escalada_por": "guardrail_saida" if por_guardrail else "pedido_do_cliente",
            "acoes_tomadas": [*estado.get("acoes_tomadas", []), "abrir_ticket"],
        }

    # --- 6. memória de longo prazo e resumo --------------------------------------------------

    def salvar_memoria(self, estado: EstadoDaConversa, runtime: Runtime) -> dict:
        memorias = estado.get("memorias") or memorias_vazias()
        salvar_memorias(
            runtime.store,
            self.deps.fabrica.trabalhador(),
            estado["cliente_id"],
            list(estado["messages"]),
            desfecho=estado.get("desfecho") or "Resolvida",
            acoes=list(estado.get("acoes_tomadas", [])),
            fatos_conhecidos=memorias["semantica"],
            guardar_fatos=not estado.get("mensagem_sensivel"),
        )
        return self._resumir_se_longa(estado)

    def _resumir_se_longa(self, estado: EstadoDaConversa) -> dict:
        """Acima do limite, tudo antes dos últimos turnos vira um resumo. O corte é sempre
        numa mensagem do Cliente, para nunca separar um pedido de Ação do seu resultado."""
        mensagens = estado["messages"]
        if len(mensagens) <= self.config.limite_mensagens_resumo:
            return {}
        do_cliente = [i for i, m in enumerate(mensagens) if isinstance(m, HumanMessage)]
        if len(do_cliente) <= TURNOS_MANTIDOS_APOS_RESUMO:
            return {}
        corte = do_cliente[-TURNOS_MANTIDOS_APOS_RESUMO]
        antigas = mensagens[:corte]
        prompt = carregar_prompt("resumir_conversa")
        resumo = self.deps.fabrica.trabalhador().invoke(
            [
                SystemMessage(
                    prompt.renderizar(
                        resumo_anterior=estado.get("resumo") or "(nenhum)",
                        mensagens=formatar_conversa(antigas, com_acoes=True),
                    )
                ),
                HumanMessage("Resuma."),
            ],
            config={"metadata": prompt.metadata()},
        )
        return {
            "resumo": str(resumo.content),
            "messages": [RemoveMessage(id=m.id) for m in antigas if m.id],
        }

    # --- prompt de sistema comum ao gerador e ao agente ------------------------------------

    def _prompt_de_sistema(
        self, prompt: Prompt, estado: EstadoDaConversa, **extras: str
    ) -> SystemMessage:
        memorias = estado.get("memorias") or memorias_vazias()
        return SystemMessage(
            prompt.renderizar(
                memoria_procedural=memorias["procedural"] or "(nenhuma)",
                memorias=formatar_memorias(memorias),
                resumo_da_conversa=estado.get("resumo") or "(nenhum)",
                critica=formatar_critica(estado),
                **extras,
            )
        )


def formatar_memorias(memorias: Memorias) -> str:
    linhas = [f"- {fato}" for fato in memorias["semantica"]]
    linhas += [
        f"- Conversa anterior ({episodio['desfecho']}): {episodio['resumo']}"
        for episodio in memorias["episodica"]
    ]
    return "\n".join(linhas) or "(nada registrado)"


def formatar_critica(estado: EstadoDaConversa) -> str:
    critica = estado.get("critica")
    if not critica:
        return ""
    return (
        "## ATENÇÃO: sua resposta anterior foi reprovada pelo Guardrail de saída\n"
        f"Resposta reprovada: {estado.get('resposta_candidata') or ''}\n"
        f"Crítica: {critica}\n"
        "Escreva uma nova resposta corrigindo exatamente esse ponto."
    )
