"""Conexões com o Postgres, abertas sempre do mesmo jeito.

`criar_pool` é o que os processos longos usam (api e worker): as conexões são reaproveitadas
e trocadas sozinhas quando caem. Elas vêm em autocommit, com linhas como dicionários e sem
prepared statements, que é o que o checkpointer e o Store do LangGraph exigem; quem precisa
de atomicidade abre `conn.transaction()` explicitamente.
"""

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

OPCOES_DO_POOL = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}


def conectar(conn_string: str, *, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(conn_string, row_factory=dict_row, autocommit=autocommit)


async def conectar_async(conn_string: str, *, autocommit: bool = False) -> psycopg.AsyncConnection:
    return await psycopg.AsyncConnection.connect(
        conn_string, row_factory=dict_row, autocommit=autocommit
    )


def criar_pool(conn_string: str, *, tamanho_maximo: int = 10) -> ConnectionPool:
    """Pool aberto e pronto para uso. Feche com `pool.close()` (ou use como `with`)."""
    return ConnectionPool(
        conn_string,
        kwargs=OPCOES_DO_POOL,
        min_size=1,
        max_size=tamanho_maximo,
        check=ConnectionPool.check_connection,
        open=True,
    )
