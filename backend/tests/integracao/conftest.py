"""Fixtures de integração: um banco Postgres novo por teste, migrado do zero, e uma sessão de
login aberta nele.

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

from ampere.acesso.sessoes import criar_sessao, marca_da_credencial
from ampere.nucleo.banco import criar_pool
from ampere.nucleo.config import Config
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


@pytest.fixture
def sessao(banco: str, pool: ConnectionPool) -> dict[str, str]:
    """O cabeçalho de uma sessão aberta direto no banco, sem passar pelo login, para os testes
    das rotas protegidas. Ela vale para os apps montados com
    `Config(database_url=banco, modelos_falsos=True)`, como os destes testes: a sessão leva a
    marca da conta dessa configuração. Quem configura outra conta sobrescreve o fixture."""
    config = Config(database_url=banco, modelos_falsos=True)
    credencial = marca_da_credencial(config.login_email, config.login_senha_hash)
    with pool.connection() as conn:
        token, _ = criar_sessao(
            conn,
            "dono@exemplo.com.br",
            credencial=credencial,
            horas=1,
            ip="127.0.0.1",
            user_agent="pytest",
        )
    return {"Authorization": f"Bearer {token}"}
