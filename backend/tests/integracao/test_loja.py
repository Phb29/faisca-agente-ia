"""Leituras da Loja no Postgres que o grafo usa fora das Ações."""

import pytest

from ampere.loja.pedidos import StoreDePedidosPostgres
from ampere.loja.seed import semear

pytestmark = pytest.mark.integracao


def test_nome_do_cliente_vem_do_cadastro(pool):
    with pool.connection() as conn:
        semear(conn)
    store = StoreDePedidosPostgres(pool)

    assert store.nome_do_cliente("cli_carla") == "Carla Menezes"
    assert store.nome_do_cliente("cli_desconhecido") is None
