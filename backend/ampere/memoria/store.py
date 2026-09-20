"""Fábricas do Store do LangGraph (em memória para testes, Postgres em produção) e namespaces."""

from collections.abc import Callable

from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres import PostgresStore

Embed = Callable[[list[str]], list[list[float]]]

SEMANTICA = "semantica"
EPISODICA = "episodica"
PROCEDURAL = "procedural"


def _index(embed: Embed, dims: int) -> dict:
    return {"dims": dims, "embed": embed, "fields": ["texto"]}


def criar_store_em_memoria(embed: Embed, *, dims: int = 384) -> InMemoryStore:
    return InMemoryStore(index=_index(embed, dims))


def criar_store_postgres(conn_string: str, embed: Embed, *, dims: int = 384) -> PostgresStore:
    """Abre uma conexão psycopg em autocommit, constrói o Store e cria as tabelas."""
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(conn_string, autocommit=True, prepare_threshold=0, row_factory=dict_row)
    store = PostgresStore(conn, index=_index(embed, dims))
    store.setup()
    return store


def namespace_semantica(cliente_id: str) -> tuple[str, str]:
    return (cliente_id, SEMANTICA)


def namespace_episodica(cliente_id: str) -> tuple[str, str]:
    return (cliente_id, EPISODICA)


def namespace_procedural(cliente_id: str) -> tuple[str, str]:
    return (cliente_id, PROCEDURAL)
