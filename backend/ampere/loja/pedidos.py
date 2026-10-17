"""Clientes, Pedidos e Reembolsos da Loja: os modelos e dois stores (em memória e Postgres).

Todo acesso a Pedido recebe o id do Cliente, então um Cliente nunca enxerga o Pedido de
outro, nem por engano do modelo.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from psycopg.rows import class_row
from psycopg_pool import ConnectionPool

STATUS_SEM_PAGAMENTO = "aguardando_pagamento"


def formatar_reais(valor: Decimal) -> str:
    """No formato que o Cliente lê: `R$ 4.899,90`."""
    inteiro, centavos = f"{valor:,.2f}".split(".")
    return f"R$ {inteiro.replace(',', '.')},{centavos}"


@dataclass(frozen=True)
class Cliente:
    id: str
    nome: str
    email: str


@dataclass(frozen=True)
class Pedido:
    id: str
    cliente_id: str
    produto: str
    linha: str
    valor: Decimal
    status: str
    data: date

    def resumo(self) -> str:
        """Uma linha que o modelo, o Atendente e o Cliente leem do mesmo jeito."""
        return (
            f"Pedido {self.id}: {self.produto} ({self.linha}), {formatar_reais(self.valor)}, "
            f"status {self.status.replace('_', ' ')}, feito em {self.data:%d/%m/%Y}"
        )


@dataclass(frozen=True)
class Reembolso:
    pedido_id: str
    cliente_id: str
    valor: Decimal
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))


class StoreDePedidos(Protocol):
    def nome_do_cliente(self, cliente_id: str) -> str | None: ...
    def listar(self, cliente_id: str) -> list[Pedido]: ...
    def obter(self, cliente_id: str, pedido_id: str) -> Pedido | None: ...
    def reembolsos_recentes(self, cliente_id: str, *, dias: int = 30) -> list[Reembolso]: ...
    def reembolso_do_pedido(self, cliente_id: str, pedido_id: str) -> Reembolso | None: ...
    def registrar_reembolso(self, reembolso: Reembolso) -> bool:
        """Grava o Reembolso e devolve True; devolve False se o Pedido já tinha um. Quem decide
        é a gravação, não a consulta de antes: duas Conversas podem consultar ao mesmo tempo."""
        ...


class StoreDePedidosEmMemoria:
    def __init__(
        self,
        pedidos: list[Pedido],
        reembolsos: list[Reembolso] | None = None,
        *,
        clientes: list[Cliente] | None = None,
    ) -> None:
        self._pedidos = list(pedidos)
        self._reembolsos = list(reembolsos or [])
        self._clientes = {c.id: c for c in clientes or []}

    def nome_do_cliente(self, cliente_id: str) -> str | None:
        cliente = self._clientes.get(cliente_id)
        return cliente.nome if cliente else None

    def listar(self, cliente_id: str) -> list[Pedido]:
        return [p for p in self._pedidos if p.cliente_id == cliente_id]

    def obter(self, cliente_id: str, pedido_id: str) -> Pedido | None:
        return next((p for p in self.listar(cliente_id) if p.id == pedido_id), None)

    def reembolsos_recentes(self, cliente_id: str, *, dias: int = 30) -> list[Reembolso]:
        limite = datetime.now(UTC) - timedelta(days=dias)
        return [r for r in self._reembolsos if r.cliente_id == cliente_id and r.criado_em >= limite]

    def reembolso_do_pedido(self, cliente_id: str, pedido_id: str) -> Reembolso | None:
        return next(
            (
                r
                for r in self._reembolsos
                if r.cliente_id == cliente_id and r.pedido_id == pedido_id
            ),
            None,
        )

    def registrar_reembolso(self, reembolso: Reembolso) -> bool:
        if any(r.pedido_id == reembolso.pedido_id for r in self._reembolsos):
            return False
        self._reembolsos.append(reembolso)
        return True


class StoreDePedidosPostgres:
    """Lê `clientes` e lê e grava em `pedidos` e `reembolsos` (ver nucleo/migracoes)."""

    COLUNAS_DO_PEDIDO = "id, cliente_id, produto, linha, valor, status, data"
    COLUNAS_DO_REEMBOLSO = "pedido_id, cliente_id, valor, criado_em"

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def nome_do_cliente(self, cliente_id: str) -> str | None:
        with self._pool.connection() as conn:
            linha = conn.execute(
                "SELECT nome FROM clientes WHERE id = %s", (cliente_id,)
            ).fetchone()
        return linha["nome"] if linha else None

    def listar(self, cliente_id: str) -> list[Pedido]:
        return self._pedidos(
            f"SELECT {self.COLUNAS_DO_PEDIDO} FROM pedidos WHERE cliente_id = %s "
            "ORDER BY data DESC",
            (cliente_id,),
        )

    def obter(self, cliente_id: str, pedido_id: str) -> Pedido | None:
        pedidos = self._pedidos(
            f"SELECT {self.COLUNAS_DO_PEDIDO} FROM pedidos WHERE cliente_id = %s AND id = %s",
            (cliente_id, pedido_id),
        )
        return pedidos[0] if pedidos else None

    def reembolsos_recentes(self, cliente_id: str, *, dias: int = 30) -> list[Reembolso]:
        return self._reembolsos(
            f"SELECT {self.COLUNAS_DO_REEMBOLSO} FROM reembolsos "
            "WHERE cliente_id = %s AND criado_em >= now() - make_interval(days => %s)",
            (cliente_id, dias),
        )

    def reembolso_do_pedido(self, cliente_id: str, pedido_id: str) -> Reembolso | None:
        reembolsos = self._reembolsos(
            f"SELECT {self.COLUNAS_DO_REEMBOLSO} FROM reembolsos "
            "WHERE cliente_id = %s AND pedido_id = %s LIMIT 1",
            (cliente_id, pedido_id),
        )
        return reembolsos[0] if reembolsos else None

    def registrar_reembolso(self, reembolso: Reembolso) -> bool:
        """O índice um_reembolso_por_pedido (migração 0006) barra o segundo Reembolso do mesmo
        Pedido, mesmo quando duas Conversas passam pela conferência ao mesmo tempo."""
        with self._pool.connection() as conn:
            inserido = conn.execute(
                "INSERT INTO reembolsos (pedido_id, cliente_id, valor) VALUES (%s, %s, %s) "
                "ON CONFLICT (pedido_id) DO NOTHING RETURNING pedido_id",
                (reembolso.pedido_id, reembolso.cliente_id, reembolso.valor),
            ).fetchone()
        return inserido is not None

    def _pedidos(self, sql: str, parametros: tuple) -> list[Pedido]:
        with self._pool.connection() as conn, conn.cursor(row_factory=class_row(Pedido)) as cur:
            return cur.execute(sql, parametros).fetchall()

    def _reembolsos(self, sql: str, parametros: tuple) -> list[Reembolso]:
        with self._pool.connection() as conn, conn.cursor(row_factory=class_row(Reembolso)) as cur:
            return cur.execute(sql, parametros).fetchall()


def listar_clientes(pool: ConnectionPool) -> list[Cliente]:
    with pool.connection() as conn, conn.cursor(row_factory=class_row(Cliente)) as cur:
        return cur.execute("SELECT id, nome, email FROM clientes ORDER BY nome").fetchall()
