"""Conexão com o Postgres. Uma função só, para todo mundo abrir conexão do mesmo jeito."""

import psycopg
from psycopg.rows import dict_row


def conectar(conn_string: str, *, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(conn_string, row_factory=dict_row, autocommit=autocommit)


async def conectar_async(conn_string: str, *, autocommit: bool = False) -> psycopg.AsyncConnection:
    return await psycopg.AsyncConnection.connect(
        conn_string, row_factory=dict_row, autocommit=autocommit
    )
