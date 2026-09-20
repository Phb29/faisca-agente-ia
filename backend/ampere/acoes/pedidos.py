"""Pedidos e Reembolsos do Cliente: leitura da tabela seed e registro de Reembolso."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Protocol


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
        return (
            f"Pedido {self.id}: {self.produto} ({self.linha}), R$ {self.valor:.2f}, "
            f"status {self.status}, feito em {self.data.isoformat()}"
        )


@dataclass(frozen=True)
class Reembolso:
    pedido_id: str
    cliente_id: str
    valor: Decimal
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))


class StoreDePedidos(Protocol):
    def listar(self, cliente_id: str) -> list[Pedido]: ...
    def obter(self, cliente_id: str, pedido_id: str) -> Pedido | None: ...
    def reembolsos_recentes(self, cliente_id: str, *, dias: int = 30) -> list[Reembolso]: ...
    def registrar_reembolso(self, reembolso: Reembolso) -> None: ...


class StoreDePedidosEmMemoria:
    def __init__(self, pedidos: list[Pedido], reembolsos: list[Reembolso] | None = None) -> None:
        self._pedidos = list(pedidos)
        self._reembolsos = list(reembolsos or [])

    def listar(self, cliente_id: str) -> list[Pedido]:
        return [p for p in self._pedidos if p.cliente_id == cliente_id]

    def obter(self, cliente_id: str, pedido_id: str) -> Pedido | None:
        return next((p for p in self.listar(cliente_id) if p.id == pedido_id), None)

    def reembolsos_recentes(self, cliente_id: str, *, dias: int = 30) -> list[Reembolso]:
        limite = datetime.now(UTC) - timedelta(days=dias)
        return [r for r in self._reembolsos if r.cliente_id == cliente_id and r.criado_em >= limite]

    def registrar_reembolso(self, reembolso: Reembolso) -> None:
        self._reembolsos.append(reembolso)


class StoreDePedidosPostgres:
    """Lê e grava nas tabelas `pedidos` e `reembolsos` (ver fila/migracoes)."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def listar(self, cliente_id: str) -> list[Pedido]:
        linhas = self._conn.execute(
            "SELECT * FROM pedidos WHERE cliente_id = %s ORDER BY data DESC", (cliente_id,)
        ).fetchall()
        return [self._pedido(linha) for linha in linhas]

    def obter(self, cliente_id: str, pedido_id: str) -> Pedido | None:
        linha = self._conn.execute(
            "SELECT * FROM pedidos WHERE cliente_id = %s AND id = %s", (cliente_id, pedido_id)
        ).fetchone()
        return self._pedido(linha) if linha else None

    def reembolsos_recentes(self, cliente_id: str, *, dias: int = 30) -> list[Reembolso]:
        linhas = self._conn.execute(
            "SELECT * FROM reembolsos WHERE cliente_id = %s AND criado_em >= now() - %s::interval",
            (cliente_id, f"{dias} days"),
        ).fetchall()
        return [
            Reembolso(
                pedido_id=r["pedido_id"],
                cliente_id=r["cliente_id"],
                valor=Decimal(r["valor"]),
                criado_em=r["criado_em"],
            )
            for r in linhas
        ]

    def registrar_reembolso(self, reembolso: Reembolso) -> None:
        self._conn.execute(
            "INSERT INTO reembolsos (pedido_id, cliente_id, valor) VALUES (%s, %s, %s)",
            (reembolso.pedido_id, reembolso.cliente_id, reembolso.valor),
        )
        self._conn.commit()

    @staticmethod
    def _pedido(linha: dict) -> Pedido:
        return Pedido(
            id=linha["id"],
            cliente_id=linha["cliente_id"],
            produto=linha["produto"],
            linha=linha["linha"],
            valor=Decimal(linha["valor"]),
            status=linha["status"],
            data=linha["data"],
        )
