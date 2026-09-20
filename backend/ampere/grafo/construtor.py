"""Monta e compila o grafo: oito nós, três caminhos do Roteador e a volta única ao gerador."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from ampere.grafo.estado import EstadoDaConversa
from ampere.grafo.nos import Dependencias, criar_nos

__all__ = ["Dependencias", "construir_grafo"]


def depois_do_guardrail_de_entrada(estado: EstadoDaConversa) -> str:
    return "salvar_memoria" if estado.get("bloqueio") else "roteador"


def depois_do_roteador(estado: EstadoDaConversa) -> str:
    return "recuperar_contexto" if estado.get("intencao") == "duvida" else "agente"


def construir_grafo(
    deps: Dependencias,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
) -> CompiledStateGraph:
    nos = criar_nos(deps)
    grafo = StateGraph(EstadoDaConversa)

    grafo.add_node("carregar_memoria", nos["carregar_memoria"])
    grafo.add_node("guardrail_entrada", nos["guardrail_entrada"])
    grafo.add_node("roteador", nos["roteador"])
    grafo.add_node("recuperar_contexto", nos["recuperar_contexto"])
    grafo.add_node("gerar_resposta", nos["gerar_resposta"])
    grafo.add_node("agente", nos["agente"], destinations=("agente", "guardrail_saida"))
    grafo.add_node(
        "guardrail_saida",
        nos["guardrail_saida"],
        destinations=("salvar_memoria", "gerar_resposta", "agente"),
    )
    grafo.add_node("salvar_memoria", nos["salvar_memoria"])

    grafo.add_edge(START, "carregar_memoria")
    grafo.add_edge("carregar_memoria", "guardrail_entrada")
    grafo.add_conditional_edges(
        "guardrail_entrada", depois_do_guardrail_de_entrada, ["salvar_memoria", "roteador"]
    )
    grafo.add_conditional_edges("roteador", depois_do_roteador, ["recuperar_contexto", "agente"])
    grafo.add_edge("recuperar_contexto", "gerar_resposta")
    grafo.add_edge("gerar_resposta", "guardrail_saida")
    grafo.add_edge("salvar_memoria", END)

    return grafo.compile(checkpointer=checkpointer, store=store, name="suporte_ampere")
