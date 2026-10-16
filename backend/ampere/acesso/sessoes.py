"""Sessões de login no Postgres.

O token vai para quem entrou e nunca é gravado: a tabela guarda só o sha256 dele, que é o id
da sessão. Quem lê o banco (ou um backup) não consegue usar uma sessão aberta. O sha256 basta,
sem sal nem custo, porque o token tem 256 bits aleatórios e não há o que adivinhar.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime

import psycopg


@dataclass(frozen=True)
class Sessao:
    email: str
    criada_em: datetime
    expira_em: datetime


def criar_sessao(
    conn: psycopg.Connection, email: str, *, horas: int, ip: str, user_agent: str
) -> tuple[str, datetime]:
    """Abre uma sessão de `horas` horas. Devolve o token e quando ele expira."""
    token = secrets.token_urlsafe(32)
    linha = conn.execute(
        "INSERT INTO sessoes (id, email, expira_em, ip, user_agent) "
        "VALUES (%s, %s, now() + make_interval(hours => %s), %s, %s) RETURNING expira_em",
        (_id(token), email, horas, ip, user_agent),
    ).fetchone()
    return token, linha["expira_em"]


def sessao_valida(conn: psycopg.Connection, token: str) -> Sessao | None:
    """A sessão do token, se existir e não tiver expirado."""
    if not token:
        return None
    linha = conn.execute(
        "SELECT email, criada_em, expira_em FROM sessoes WHERE id = %s AND expira_em > now()",
        (_id(token),),
    ).fetchone()
    return Sessao(**linha) if linha else None


def encerrar_sessao(conn: psycopg.Connection, token: str) -> None:
    """Apaga a sessão. Sessão que já não existe não é erro."""
    conn.execute("DELETE FROM sessoes WHERE id = %s", (_id(token),))


def limpar_expiradas(conn: psycopg.Connection) -> int:
    return conn.execute("DELETE FROM sessoes WHERE expira_em <= now()").rowcount


def _id(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
