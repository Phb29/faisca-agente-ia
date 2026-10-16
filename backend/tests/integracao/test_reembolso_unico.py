"""O banco garante um Reembolso por Pedido, mesmo com duas Conversas gravando juntas."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from ampere.loja.pedidos import Reembolso, StoreDePedidosPostgres
from ampere.loja.seed import semear

pytestmark = pytest.mark.integracao


def test_segundo_reembolso_do_mesmo_pedido_nao_entra(pool):
    with pool.connection() as conn:
        semear(conn)
    store = StoreDePedidosPostgres(pool)
    reembolso = Reembolso(pedido_id="P1002", cliente_id="cli_ana", valor=Decimal("199.90"))

    assert store.registrar_reembolso(reembolso) is True
    assert store.registrar_reembolso(reembolso) is False


def test_duas_conversas_gravando_ao_mesmo_tempo_deixam_um_reembolso(pool):
    with pool.connection() as conn:
        semear(conn)
    store = StoreDePedidosPostgres(pool)
    reembolso = Reembolso(pedido_id="P1002", cliente_id="cli_ana", valor=Decimal("199.90"))

    with ThreadPoolExecutor(max_workers=4) as executor:
        resultados = list(executor.map(lambda _: store.registrar_reembolso(reembolso), range(4)))

    assert sorted(resultados) == [False, False, False, True]
    with pool.connection() as conn:
        linha = conn.execute(
            "SELECT count(*) AS total FROM reembolsos WHERE pedido_id = 'P1002'"
        ).fetchone()
    assert linha["total"] == 1
