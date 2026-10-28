"""Monta e compila o grafo: nove nós, três caminhos do Roteador, uma volta de correção
pelo Guardrail de saída e o desvio para escalar."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from ampere.grafo.estado import EstadoDaConversa
from ampere.grafo.nos import Dependencias, NosDoGrafo

__all__ = ["Dependencias", "construir_grafo"]

CAMINHO_POR_INTENCAO = {
    "duvida": "recuperar_contexto",
    "transacao": "agente",
    "quer_humano": "escalar",
}


def depois_do_guardrail_de_entrada(estado: EstadoDaConversa) -> str:
    return "salvar_memoria" if estado.get("bloqueio") else "roteador"


def depois_do_roteador(estado: EstadoDaConversa) -> str:
    return estado["intencao"] or "duvida"


def construir_grafo(
    deps: Dependencias,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
) -> CompiledStateGraph:
    nos = NosDoGrafo(deps)
    grafo = StateGraph(EstadoDaConversa)

    # Definição dos Nós
    grafo.add_node("carregar_memoria", nos.carregar_memoria)
    grafo.add_node("guardrail_entrada", nos.guardrail_entrada)
    grafo.add_node("roteador", nos.roteador)
    grafo.add_node("recuperar_contexto", nos.recuperar_contexto)
    grafo.add_node("gerar_resposta", nos.gerar_resposta)
    grafo.add_node("agente", nos.agente, destinations=("agente", "guardrail_saida"))
    grafo.add_node(
        "guardrail_saida",
        nos.guardrail_saida,
        destinations=("salvar_memoria", "gerar_resposta", "agente", "escalar"),
    )
    grafo.add_node("escalar", nos.escalar)
    grafo.add_node("salvar_memoria", nos.salvar_memoria)

    # Definição das Arestas
    grafo.add_edge(START, "carregar_memoria")
    grafo.add_edge("carregar_memoria", "guardrail_entrada")
    grafo.add_conditional_edges(
        "guardrail_entrada", depois_do_guardrail_de_entrada, ["salvar_memoria", "roteador"]
    )
    grafo.add_conditional_edges("roteador", depois_do_roteador, CAMINHO_POR_INTENCAO)
    grafo.add_edge("recuperar_contexto", "gerar_resposta")
    grafo.add_edge("gerar_resposta", "guardrail_saida")
    grafo.add_edge("escalar", "salvar_memoria")
    grafo.add_edge("salvar_memoria", END)

    return grafo.compile(checkpointer=checkpointer, store=store, name="faisca")
