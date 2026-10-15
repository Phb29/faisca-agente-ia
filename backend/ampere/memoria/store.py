"""O Store do LangGraph (em memória nos testes, Postgres em produção) e os namespaces.

Cada Cliente tem o próprio namespace, então a busca de um Cliente nunca alcança a memória
de outro. Só a Memória Semântica é indexada por embedding; as outras são lidas por chave.
"""

from collections.abc import Callable

from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres import PostgresStore
from psycopg_pool import ConnectionPool

Embed = Callable[[list[str]], list[list[float]]]

SEMANTICA = "semantica"
EPISODICA = "episodica"
PROCEDURAL = "procedural"


def _indice(embed: Embed, dims: int) -> dict:
    return {"dims": dims, "embed": embed, "fields": ["texto"]}


def criar_store_em_memoria(embed: Embed, *, dims: int = 384) -> InMemoryStore:
    return InMemoryStore(index=_indice(embed, dims))


def criar_store_postgres(pool: ConnectionPool, embed: Embed, *, dims: int = 384) -> PostgresStore:
    """Store sobre o pool; `setup` cria as tabelas do índice vetorial (idempotente)."""
    store = PostgresStore(pool, index=_indice(embed, dims))
    store.setup()
    return store


def namespace_semantica(cliente_id: str) -> tuple[str, str]:
    return (cliente_id, SEMANTICA)


def namespace_episodica(cliente_id: str) -> tuple[str, str]:
    return (cliente_id, EPISODICA)


def namespace_procedural(cliente_id: str) -> tuple[str, str]:
    return (cliente_id, PROCEDURAL)
