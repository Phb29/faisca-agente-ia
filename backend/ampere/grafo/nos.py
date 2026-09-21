"""Os oito nós do grafo, na ordem em que uma mensagem os atravessa.

carregar_memoria → guardrail_entrada → roteador → (recuperar_contexto → gerar_resposta |
agente) → guardrail_saida → salvar_memoria. Cada nó é uma função pura sobre o estado que
recebe as dependências (modelos, retriever, stores) por fechamento, via `criar_nos`.
"""

from dataclasses import dataclass
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.runtime import Runtime
from langgraph.types import Command

from ampere.acoes.pedidos import StoreDePedidos
from ampere.acoes.ticket import StoreDeTickets, abrir_ticket
from ampere.acoes.tools import ContextoDoTurno, anunciar, criar_tools
from ampere.grafo.estado import EstadoDaConversa, Memorias, memorias_vazias
from ampere.grafo.prompts import Prompt, carregar_prompt
from ampere.guardrails.entrada import RESPOSTAS_FIXAS, avaliar_entrada
from ampere.guardrails.mascaramento import mascarar
from ampere.guardrails.saida import RESPOSTA_ESCALADA, avaliar_saida
from ampere.memoria.carregar import carregar_memorias
from ampere.memoria.salvar import salvar_memorias
from ampere.nucleo.config import Config
from ampere.nucleo.mensagens import formatar_conversa
from ampere.nucleo.modelos import FabricaDeModelos
from ampere.observabilidade.langfuse import Observabilidade
from ampere.rag.busca import Retriever, formatar_chunks
from ampere.roteador.roteador import rotear

RESPOSTA_TICKET_ABERTO = (
    "Entendi. Abri um Ticket para um Atendente humano continuar o seu atendimento. "
    "Você receberá o retorno em breve."
)
MENSAGENS_MANTIDAS_APOS_RESUMO = 4


@dataclass
class Dependencias:
    config: Config
    fabrica: FabricaDeModelos
    retriever: Retriever
    pedidos: StoreDePedidos
    tickets: StoreDeTickets
    observabilidade: Observabilidade


def ultima_mensagem_do_cliente(messages: list[BaseMessage]) -> str:
    for mensagem in reversed(messages):
        if isinstance(mensagem, HumanMessage):
            return str(mensagem.content)
    return ""


def formatar_memorias(memorias: Memorias) -> str:
    linhas = [f"- {fato}" for fato in memorias["semantica"]]
    for episodio in memorias["episodica"]:
        linhas.append(
            f"- Conversa anterior ({episodio.get('desfecho', '')}): {episodio.get('resumo', '')}"
        )
    return "\n".join(linhas) or "(nada registrado)"


def formatar_critica(estado: EstadoDaConversa) -> str:
    critica = estado.get("critica")
    if not critica:
        return ""
    return (
        "ATENÇÃO: sua resposta anterior foi rejeitada pelo Guardrail de saída.\n"
        f"Resposta rejeitada: {estado.get('resposta_candidata') or ''}\n"
        f"Crítica: {critica}\nEscreva uma nova resposta corrigindo exatamente esse ponto."
    )


def prompt_de_sistema(prompt: Prompt, estado: EstadoDaConversa, **extras: str) -> SystemMessage:
    memorias = estado.get("memorias") or memorias_vazias()
    texto = prompt.renderizar(
        memoria_procedural=memorias["procedural"] or "(nenhuma)",
        memorias=formatar_memorias(memorias),
        critica=formatar_critica(estado),
        **extras,
    )
    if estado.get("resumo"):
        texto += f"\n\nResumo das mensagens anteriores desta Conversa:\n{estado['resumo']}"
    return SystemMessage(texto)


def criar_nos(deps: Dependencias) -> dict[str, object]:
    config = deps.config
    obs = deps.observabilidade

    def carregar_memoria(estado: EstadoDaConversa, runtime: Runtime) -> dict:
        mensagem = ultima_mensagem_do_cliente(estado["messages"])
        memorias = carregar_memorias(runtime.store, estado["cliente_id"], mensagem)
        return {
            "memorias": memorias,
            "mensagem_sensivel": False,
            "bloqueio": None,
            "intencao": None,
            "contexto": [],
            "resposta_candidata": None,
            "critica": None,
            "tentativas": 0,
            "acoes_tomadas": [],
            "desfecho": None,
        }

    def guardrail_entrada(estado: EstadoDaConversa) -> dict:
        original = next(m for m in reversed(estado["messages"]) if isinstance(m, HumanMessage))
        resultado = avaliar_entrada(
            deps.fabrica.jev(), str(original.content), limiar=config.limiar_guardrail_entrada
        )
        obs.registrar_jev(
            "guardrail_entrada",
            {"mensagem": str(original.content)},
            resultado.respostas,
            metadata={"limiar": config.limiar_guardrail_entrada, "bloqueio": resultado.bloqueio},
        )
        atualizacao: dict = {
            "mensagem_sensivel": resultado.sensivel,
            "bloqueio": resultado.bloqueio,
        }
        mensagens: list[BaseMessage] = []
        if resultado.sensivel:
            mensagens.append(HumanMessage(content=mascarar(str(original.content)), id=original.id))
        if resultado.bloqueio:
            mensagens.append(AIMessage(RESPOSTAS_FIXAS[resultado.bloqueio]))
            atualizacao["resposta_candidata"] = RESPOSTAS_FIXAS[resultado.bloqueio]
            atualizacao["desfecho"] = "Resolvida"
        if mensagens:
            atualizacao["messages"] = mensagens
        return atualizacao

    def roteador(estado: EstadoDaConversa) -> dict:
        mensagem = ultima_mensagem_do_cliente(estado["messages"])
        roteamento = rotear(deps.fabrica.jev(), mensagem, estado["memorias"])
        obs.registrar_jev(
            "roteador",
            {"mensagem": mensagem},
            roteamento.respostas,
            metadata={"intencao": roteamento.intencao},
        )
        return {"intencao": roteamento.intencao}

    def recuperar_contexto(estado: EstadoDaConversa) -> dict:
        mensagem = ultima_mensagem_do_cliente(estado["messages"])
        anunciar("consultar_base_de_conhecimento", {"pergunta": mensagem})
        chunks = deps.retriever.buscar(mensagem, k=5)
        return {
            "contexto": [chunk.model_dump() for chunk in chunks],
            "acoes_tomadas": ["consultar_base_de_conhecimento"],
        }

    def gerar_resposta(estado: EstadoDaConversa) -> dict:
        prompt = carregar_prompt("gerar_resposta")
        sistema = prompt_de_sistema(prompt, estado, contexto=formatar_chunks(estado["contexto"]))
        resposta = deps.fabrica.gerador().invoke(
            [sistema, *estado["messages"]], config={"metadata": prompt.metadata()}
        )
        return {"resposta_candidata": str(resposta.content)}

    def agente(estado: EstadoDaConversa) -> Command[Literal["agente", "guardrail_saida"]]:
        turno = ContextoDoTurno(
            cliente_id=estado["cliente_id"],
            conversa_id=estado.get("conversa_id", ""),
            messages=list(estado["messages"]),
        )
        if estado.get("intencao") == "quer_humano" and not estado.get("acoes_tomadas"):
            anunciar("abrir_ticket", {"motivo": "Cliente pediu para falar com uma pessoa"})
            abrir_ticket(
                deps.fabrica.trabalhador(),
                deps.tickets,
                conversa_id=turno.conversa_id,
                cliente_id=turno.cliente_id,
                messages=turno.messages,
            )
            return Command(
                goto="guardrail_saida",
                update={
                    "resposta_candidata": RESPOSTA_TICKET_ABERTO,
                    "acoes_tomadas": ["abrir_ticket"],
                    "desfecho": "Escalada",
                },
            )

        tools = criar_tools(
            deps.fabrica,
            config,
            retriever=deps.retriever,
            pedidos=deps.pedidos,
            tickets=deps.tickets,
            turno=turno,
            observabilidade=obs,
        )
        ultima = estado["messages"][-1]
        if isinstance(ultima, AIMessage) and ultima.tool_calls:
            por_nome = {t.name: t for t in tools}
            resultados = [
                ToolMessage(
                    content=str(por_nome[chamada["name"]].invoke(chamada["args"])),
                    tool_call_id=chamada["id"],
                    name=chamada["name"],
                )
                for chamada in ultima.tool_calls
            ]
            return Command(
                goto="agente",
                update={
                    "messages": resultados,
                    "acoes_tomadas": [*estado.get("acoes_tomadas", []), *turno.acoes_tomadas],
                    "contexto": [*estado.get("contexto", []), *turno.contexto],
                    **({"desfecho": "Escalada"} if turno.escalada else {}),
                },
            )

        prompt = carregar_prompt("agente")
        modelo: BaseChatModel = deps.fabrica.gerador().bind_tools(tools)
        resposta = modelo.invoke(
            [prompt_de_sistema(prompt, estado), *estado["messages"]],
            config={"metadata": prompt.metadata()},
        )
        if resposta.tool_calls:
            return Command(goto="agente", update={"messages": [resposta]})
        return Command(goto="guardrail_saida", update={"resposta_candidata": str(resposta.content)})

    def guardrail_saida(
        estado: EstadoDaConversa,
    ) -> Command[Literal["salvar_memoria", "gerar_resposta", "agente"]]:
        candidata = estado.get("resposta_candidata") or ""
        resultado = avaliar_saida(
            deps.fabrica.jev(),
            candidata,
            contexto=[c.get("texto", "") for c in estado.get("contexto", [])],
            acoes=list(estado.get("acoes_tomadas", [])),
            limiar=config.limiar_guardrail_saida,
        )
        obs.registrar_jev(
            "guardrail_saida",
            {"resposta": candidata},
            resultado.respostas,
            metadata={"limiar": config.limiar_guardrail_saida, "motivo": resultado.motivo},
        )
        if resultado.aprovada:
            return Command(
                goto="salvar_memoria",
                update={
                    "messages": [AIMessage(candidata)],
                    "desfecho": estado.get("desfecho") or "Resolvida",
                },
            )
        if estado.get("tentativas", 0) < 1:
            origem = "gerar_resposta" if estado.get("intencao") == "duvida" else "agente"
            return Command(
                goto=origem,
                update={
                    "critica": resultado.critica,
                    "tentativas": estado.get("tentativas", 0) + 1,
                },
            )
        anunciar("abrir_ticket", {"motivo": f"guardrail de saída: {resultado.motivo}"})
        abrir_ticket(
            deps.fabrica.trabalhador(),
            deps.tickets,
            conversa_id=estado.get("conversa_id", ""),
            cliente_id=estado["cliente_id"],
            messages=[*estado["messages"], AIMessage(candidata)],
        )
        return Command(
            goto="salvar_memoria",
            update={
                "messages": [AIMessage(RESPOSTA_ESCALADA)],
                "desfecho": "Escalada",
                "acoes_tomadas": [*estado.get("acoes_tomadas", []), "abrir_ticket"],
            },
        )

    def salvar_memoria(estado: EstadoDaConversa, runtime: Runtime) -> dict:
        trabalhador = deps.fabrica.trabalhador()
        salvar_memorias(
            runtime.store,
            trabalhador,
            estado["cliente_id"],
            list(estado["messages"]),
            desfecho=estado.get("desfecho") or "Resolvida",
            acoes=list(estado.get("acoes_tomadas", [])),
            fatos_conhecidos=(estado.get("memorias") or memorias_vazias())["semantica"],
        )
        mensagens = estado["messages"]
        if len(mensagens) <= config.limite_mensagens_resumo:
            return {}
        antigas = mensagens[:-MENSAGENS_MANTIDAS_APOS_RESUMO]
        prompt = carregar_prompt("resumir_conversa")
        resumo = trabalhador.invoke(
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

    return {
        "carregar_memoria": carregar_memoria,
        "guardrail_entrada": guardrail_entrada,
        "roteador": roteador,
        "recuperar_contexto": recuperar_contexto,
        "gerar_resposta": gerar_resposta,
        "agente": agente,
        "guardrail_saida": guardrail_saida,
        "salvar_memoria": salvar_memoria,
    }
