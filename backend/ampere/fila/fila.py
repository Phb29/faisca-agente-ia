"""A fila de jobs no Postgres: enfileirar, reservar com SKIP LOCKED e concluir.

Enfileirar também avisa os workers com `NOTIFY fila_de_jobs`, dentro da mesma transação: o
aviso só sai se o job foi gravado, e o worker acorda na hora em vez de esperar a próxima
volta do polling.
"""

from dataclasses import dataclass
from typing import Literal

import psycopg
from psycopg.types.json import Jsonb

from ampere.conversas.conversas import atualizar_status, gravar_mensagem, titulo_a_partir_de

CANAL_DA_FILA = "fila_de_jobs"
TipoDeJob = Literal["mensagem", "retomada"]


@dataclass(frozen=True)
class Job:
    id: int
    tipo: TipoDeJob
    conversa_id: str
    message_id: str | None
    payload: dict


def enfileirar_mensagem(
    conn: psycopg.Connection, conversa_id: str, message_id: str, conteudo: str, cliente_id: str
) -> bool:
    """Grava a mensagem do Cliente e o job numa transação só. Devolve False quando o
    `message_id` já existia: o reenvio é ignorado sem erro (idempotência)."""
    with conn.transaction():
        if gravar_mensagem(conn, conversa_id, "cliente", conteudo, message_id) is None:
            return False
        conn.execute(
            "INSERT INTO fila_de_jobs (tipo, conversa_id, message_id, payload) "
            "VALUES ('mensagem', %s, %s, %s)",
            (conversa_id, message_id, Jsonb({"conteudo": conteudo, "cliente_id": cliente_id})),
        )
        atualizar_status(conn, conversa_id, "aberta", titulo_se_vazio=titulo_a_partir_de(conteudo))
        _avisar_workers(conn)
    return True


def enfileirar_retomada(
    conn: psycopg.Connection,
    conversa_id: str,
    aprovacao_id: str,
    aprovado: bool,
    motivo: str | None,
    cliente_id: str,
) -> int:
    """Job que retoma a Conversa congelada com a decisão do Atendente."""
    payload = {
        "aprovacao_id": str(aprovacao_id),
        "aprovado": aprovado,
        "motivo": motivo,
        "cliente_id": cliente_id,
    }
    with conn.transaction():
        linha = conn.execute(
            "INSERT INTO fila_de_jobs (tipo, conversa_id, payload) "
            "VALUES ('retomada', %s, %s) RETURNING id",
            (conversa_id, Jsonb(payload)),
        ).fetchone()
        _avisar_workers(conn)
    return linha["id"]


def pegar_proximo_job(conn: psycopg.Connection) -> Job | None:
    """Reserva o job pendente mais antigo com `FOR UPDATE SKIP LOCKED`: dois workers nunca
    pegam o mesmo e nenhum espera o outro."""
    with conn.transaction():
        linha = conn.execute(
            """
            UPDATE fila_de_jobs SET status = 'processando', iniciado_em = now()
            WHERE id = (
                SELECT id FROM fila_de_jobs WHERE status = 'pendente'
                ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
            )
            RETURNING id, tipo, conversa_id::text, message_id, payload
            """
        ).fetchone()
    return Job(**linha) if linha else None


def concluir_job(conn: psycopg.Connection, job_id: int, erro: str | None = None) -> None:
    conn.execute(
        "UPDATE fila_de_jobs SET status = %s, concluido_em = now(), erro = %s WHERE id = %s",
        ("erro" if erro else "concluido", erro, job_id),
    )


def _avisar_workers(conn: psycopg.Connection) -> None:
    conn.execute(f"NOTIFY {CANAL_DA_FILA}")
