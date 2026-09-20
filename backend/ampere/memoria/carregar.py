"""Carrega as três memórias de um Cliente do Store no início de cada turno."""

from langgraph.store.base import BaseStore

from ampere.grafo.estado import Memorias
from ampere.memoria.store import namespace_episodica, namespace_procedural, namespace_semantica

CHAVE_PROCEDURAL = "instrucoes"


def carregar_memorias(
    store: BaseStore,
    cliente_id: str,
    mensagem: str,
    *,
    limite_semantica: int = 5,
    limite_episodica: int = 3,
) -> Memorias:
    """Semântica por similaridade com a mensagem, episódica pelos mais recentes, procedural."""
    semantica = [
        item.value["texto"]
        for item in store.search(
            namespace_semantica(cliente_id), query=mensagem, limit=limite_semantica
        )
    ]
    episodios = store.search(namespace_episodica(cliente_id), limit=1000)
    episodios.sort(key=lambda item: item.value.get("data", ""), reverse=True)
    episodica = [
        {
            "resumo": item.value.get("resumo", ""),
            "desfecho": item.value.get("desfecho", ""),
            "acoes": list(item.value.get("acoes", [])),
            "data": item.value.get("data", ""),
        }
        for item in episodios[:limite_episodica]
    ]
    return {
        "semantica": semantica,
        "episodica": episodica,
        "procedural": ler_procedural(store, cliente_id),
    }


def ler_procedural(store: BaseStore, cliente_id: str) -> str:
    item = store.get(namespace_procedural(cliente_id), CHAVE_PROCEDURAL)
    return str(item.value.get("texto", "")) if item else ""
