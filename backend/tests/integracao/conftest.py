"""Fixtures de integração: um banco Postgres novo por teste, migrado do zero.

Os testes daqui pulam quando `DATABASE_URL` não está no ambiente. Cada teste recebe um
banco `ampere_test_<hex>` criado a partir da URL base e apagado ao fim, para que nenhum
teste enxergue o estado deixado por outro.
"""

import os
import secrets
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg_pool import ConnectionPool

from ampere.nucleo.banco import criar_pool
from ampere.nucleo.migracao import migrar

pytestmark = pytest.mark.integracao


def _url_base() -> str | None:
    return os.environ.get("DATABASE_URL")


@pytest.fixture(scope="function")
def banco() -> Iterator[str]:
    url = _url_base()
    if not url:
        pytest.skip("DATABASE_URL não definida; teste de integração pulado")

    nome = f"ampere_test_{secrets.token_hex(4)}"
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))

    info = psycopg.conninfo.conninfo_to_dict(url)
    info["dbname"] = nome
    url_teste = psycopg.conninfo.make_conninfo(**info)
    try:
        migrar(url_teste)
        yield url_teste
    finally:
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome))
            )


@pytest.fixture
def pool(banco: str) -> Iterator[ConnectionPool]:
    """Pool do banco do teste, fechado antes de o banco ser apagado."""
    pool = criar_pool(banco, tamanho_maximo=4)
    try:
        yield pool
    finally:
        pool.close()
