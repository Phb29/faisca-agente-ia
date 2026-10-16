"""Carrega as três memórias de um Cliente do Store no início de cada turno."""

from langgraph.store.base import BaseStore

from ampere.memoria.procedural import ler_preferencias, ler_procedural
from ampere.memoria.store import namespace_episodica, namespace_semantica
from ampere.memoria.tipos import Episodio, Memorias


def carregar_memorias(
    store: BaseStore,
    cliente_id: str,
    mensagem: str,
    *,
    limite_semantica: int = 5,
    limite_episodica: int = 3,
    conversa_atual: str | None = None,
) -> Memorias:
    """Semântica por similaridade com a mensagem, episódica da mais recente para a mais
    antiga, e a procedural inteira, com as instruções do Atendente e as preferências do
    Cliente."""
    semantica = [
        item.value["texto"]
        for item in store.search(
            namespace_semantica(cliente_id), query=mensagem, limit=limite_semantica
        )
    ]
    # o episódio da Conversa atual fica de fora: ela já está inteira nas mensagens
    episodios = [
        item
        for item in store.search(namespace_episodica(cliente_id), limit=1000)
        if item.key != conversa_atual
    ]
    episodios.sort(key=lambda item: item.value.get("data", ""), reverse=True)
    episodica: list[Episodio] = [
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
        "preferencias": ler_preferencias(store, cliente_id),
    }
