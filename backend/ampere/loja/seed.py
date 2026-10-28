"""Dados seed da Loja: três Clientes, seus Pedidos e um Reembolso recente.

Os ids são fixos e referenciados pelos goldens dos evals. `semear` é idempotente:
rodar duas vezes não duplica nada.
"""

from datetime import date
from decimal import Decimal

CLIENTES: list[dict] = [
    {"id": "cli_ana", "nome": "Ana Ribeiro", "email": "ana@exemplo.com"},
    {"id": "cli_bruno", "nome": "Bruno Tavares", "email": "bruno@exemplo.com"},
    {"id": "cli_carla", "nome": "Carla Menezes", "email": "carla@exemplo.com"},
]

PEDIDOS: list[dict] = [
    {
        "id": "P1001",
        "cliente_id": "cli_ana",
        "produto": "Notebook Faísca Vega 15",
        "linha": "notebooks",
        "valor": Decimal("4899.90"),
        "status": "entregue",
        "data": date(2026, 8, 12),
    },
    {
        "id": "P1002",
        "cliente_id": "cli_ana",
        "produto": "Fone Faísca Beat",
        "linha": "acessorios",
        "valor": Decimal("249.90"),
        "status": "entregue",
        "data": date(2026, 9, 2),
    },
    {
        "id": "P1003",
        "cliente_id": "cli_ana",
        "produto": "Capa Faísca Shell",
        "linha": "acessorios",
        "valor": Decimal("89.90"),
        "status": "em_transporte",
        "data": date(2026, 9, 15),
    },
    {
        "id": "P2001",
        "cliente_id": "cli_bruno",
        "produto": "Celular Faísca Pulse",
        "linha": "celulares",
        "valor": Decimal("2799.00"),
        "status": "em_transporte",
        "data": date(2026, 9, 10),
    },
    {
        "id": "P2002",
        "cliente_id": "cli_bruno",
        "produto": "Carregador Faísca Flash 65W",
        "linha": "acessorios",
        "valor": Decimal("199.90"),
        "status": "entregue",
        "data": date(2026, 8, 28),
    },
    {
        "id": "P2003",
        "cliente_id": "cli_bruno",
        "produto": "Notebook Faísca Orion 14",
        "linha": "notebooks",
        "valor": Decimal("3499.00"),
        "status": "aguardando_pagamento",
        "data": date(2026, 9, 18),
    },
    {
        "id": "P3001",
        "cliente_id": "cli_carla",
        "produto": "Celular Faísca Pulse Mini",
        "linha": "celulares",
        "valor": Decimal("1899.00"),
        "status": "devolvido",
        "data": date(2026, 8, 20),
    },
    {
        "id": "P3002",
        "cliente_id": "cli_carla",
        "produto": "Capa Faísca Shell",
        "linha": "acessorios",
        "valor": Decimal("89.90"),
        "status": "entregue",
        "data": date(2026, 9, 5),
    },
    {
        "id": "P3003",
        "cliente_id": "cli_carla",
        "produto": "Notebook Faísca Vega 15",
        "linha": "notebooks",
        "valor": Decimal("4899.90"),
        "status": "cancelado",
        "data": date(2026, 7, 30),
    },
]

# Reembolso recente de cli_carla: sinal de risco que o Gate de Aprovação considera.
REEMBOLSOS: list[dict] = [
    {"pedido_id": "P3001", "cliente_id": "cli_carla", "valor": Decimal("1899.00")},
]


def semear(conn) -> dict[str, int]:
    """Insere Clientes, Pedidos e Reembolsos sem duplicar. Devolve o total inserido por tabela."""
    inseridos = {"clientes": 0, "pedidos": 0, "reembolsos": 0}
    with conn.cursor() as cur:
        for cliente in CLIENTES:
            cur.execute(
                "INSERT INTO clientes (id, nome, email) VALUES (%(id)s, %(nome)s, %(email)s) "
                "ON CONFLICT (id) DO NOTHING",
                cliente,
            )
            inseridos["clientes"] += cur.rowcount
        for pedido in PEDIDOS:
            cur.execute(
                "INSERT INTO pedidos (id, cliente_id, produto, linha, valor, status, data) "
                "VALUES (%(id)s, %(cliente_id)s, %(produto)s, %(linha)s, %(valor)s, "
                "%(status)s, %(data)s) ON CONFLICT (id) DO NOTHING",
                pedido,
            )
            inseridos["pedidos"] += cur.rowcount
        for reembolso in REEMBOLSOS:
            cur.execute(
                "INSERT INTO reembolsos (pedido_id, cliente_id, valor) "
                "SELECT %(pedido_id)s, %(cliente_id)s, %(valor)s "
                "WHERE NOT EXISTS (SELECT 1 FROM reembolsos WHERE pedido_id = %(pedido_id)s)",
                reembolso,
            )
            inseridos["reembolsos"] += cur.rowcount
    conn.commit()
    return inseridos
