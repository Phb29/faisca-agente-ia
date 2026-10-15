"""Aprovações Pendentes: o Reembolso que o Gate tirou do fluxo automático, esperando a
decisão de um Atendente com a Conversa congelada.

O worker cria a Aprovação quando o grafo interrompe; a API lista e registra a decisão.
Decidir só funciona uma vez: a segunda tentativa não encontra a linha pendente.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import psycopg
from psycopg.rows import class_row

StatusDaAprovacao = Literal["pendente", "aprovada", "rejeitada"]


@dataclass(frozen=True)
class Aprovacao:
    id: str
    conversa_id: str
    cliente_id: str
    pedido_id: str
    valor: float
    probabilidade: float
    motivo_do_gate: str | None
    resumo: str
    status: StatusDaAprovacao
    motivo: str | None
    criada_em: datetime
    decidida_em: datetime | None


SELECT_APROVACAO = (
    "SELECT id::text, conversa_id::text, cliente_id, pedido_id, valor::float8 AS valor, "
    "probabilidade, motivo_do_gate, resumo, status, motivo, criada_em, decidida_em "
    "FROM aprovacoes_pendentes"
)


def criar_aprovacao(
    conn: psycopg.Connection,
    *,
    conversa_id: str,
    cliente_id: str,
    pedido_id: str,
    valor: float,
    probabilidade: float,
    resumo: str,
    motivo_do_gate: str | None = None,
) -> str:
    linha = conn.execute(
        "INSERT INTO aprovacoes_pendentes "
        "(conversa_id, cliente_id, pedido_id, valor, probabilidade, resumo, motivo_do_gate) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id::text",
        (conversa_id, cliente_id, pedido_id, valor, probabilidade, resumo, motivo_do_gate),
    ).fetchone()
    return linha["id"]


def listar_pendentes(conn: psycopg.Connection) -> list[Aprovacao]:
    with conn.cursor(row_factory=class_row(Aprovacao)) as cur:
        sql = f"{SELECT_APROVACAO} WHERE status = 'pendente' ORDER BY criada_em"
        return cur.execute(sql).fetchall()


def obter_aprovacao(conn: psycopg.Connection, aprovacao_id: str) -> Aprovacao | None:
    with conn.cursor(row_factory=class_row(Aprovacao)) as cur:
        return cur.execute(f"{SELECT_APROVACAO} WHERE id = %s", (aprovacao_id,)).fetchone()


def decidir_aprovacao(
    conn: psycopg.Connection, aprovacao_id: str, aprovada: bool, motivo: str | None = None
) -> Aprovacao | None:
    """Registra a decisão se a Aprovação ainda estiver pendente; senão devolve None."""
    atualizadas = conn.execute(
        "UPDATE aprovacoes_pendentes SET status = %s, motivo = %s, decidida_em = now() "
        "WHERE id = %s AND status = 'pendente'",
        ("aprovada" if aprovada else "rejeitada", motivo, aprovacao_id),
    ).rowcount
    return obter_aprovacao(conn, aprovacao_id) if atualizadas else None
