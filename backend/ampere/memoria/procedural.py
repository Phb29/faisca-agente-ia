"""Memória Procedural: instruções livres do Atendente sobre como atender um Cliente, uma
única entrada por Cliente, lida no início de cada turno e editada pela Tela do Atendente."""

from langgraph.store.base import BaseStore

from ampere.memoria.store import namespace_procedural

CHAVE = "instrucoes"


def ler_procedural(store: BaseStore, cliente_id: str) -> str:
    item = store.get(namespace_procedural(cliente_id), CHAVE)
    return str(item.value.get("texto", "")) if item else ""


def escrever_procedural(store: BaseStore, cliente_id: str, texto: str) -> None:
    store.put(namespace_procedural(cliente_id), CHAVE, {"texto": texto}, index=False)


class MemoriaProcedural:
    """O que a API usa para ler e editar a Memória Procedural, sobre o Store do LangGraph."""

    def __init__(self, store: BaseStore) -> None:
        self._store = store

    def ler(self, cliente_id: str) -> str:
        return ler_procedural(self._store, cliente_id)

    def escrever(self, cliente_id: str, texto: str) -> None:
        escrever_procedural(self._store, cliente_id, texto.strip())
