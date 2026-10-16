"""Sessões de login no Postgres.

O token vai para quem entrou e nunca é gravado: a tabela guarda só o sha256 dele, que é o id
da sessão. Quem lê o banco (ou um backup) não consegue usar uma sessão aberta. O sha256 basta,
sem sal nem custo, porque o token tem 256 bits aleatórios e não há o que adivinhar.

Cada sessão guarda também a marca da credencial com que foi aberta: 16 caracteres do sha256
do e-mail e do hash da senha da conta. Trocar a senha ou o e-mail muda a marca, e as sessões
abertas antes deixam de valer, sem precisar apagar nada.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime

import psycopg

from ampere.acesso.tentativas import normalizar


@dataclass(frozen=True)
class Sessao:
    email: str
    criada_em: datetime
    expira_em: datetime


def marca_da_credencial(email: str, senha_hash: str) -> str:
    """A marca da conta configurada. Caixa e espaços nas pontas não mudam a conta."""
    credencial = f"{normalizar(email)}\n{senha_hash.strip()}"
    return hashlib.sha256(credencial.encode()).hexdigest()[:16]


def criar_sessao(
    conn: psycopg.Connection,
    email: str,
    *,
    credencial: str,
    horas: int,
    ip: str,
    user_agent: str,
) -> tuple[str, datetime]:
    """Abre uma sessão de `horas` horas. Devolve o token e quando ele expira."""
    token = secrets.token_urlsafe(32)
    linha = conn.execute(
        "INSERT INTO sessoes (id, email, credencial, expira_em, ip, user_agent) "
        "VALUES (%s, %s, %s, now() + make_interval(hours => %s), %s, %s) RETURNING expira_em",
        (_id(token), email, credencial, horas, ip, user_agent),
    ).fetchone()
    return token, linha["expira_em"]


def sessao_valida(conn: psycopg.Connection, token: str, *, credencial: str) -> Sessao | None:
    """A sessão do token, se existir, não tiver expirado e for da credencial atual."""
    if not token:
        return None
    linha = conn.execute(
        "SELECT email, criada_em, expira_em FROM sessoes "
        "WHERE id = %s AND credencial = %s AND expira_em > now()",
        (_id(token), credencial),
    ).fetchone()
    return Sessao(**linha) if linha else None


def encerrar_sessao(conn: psycopg.Connection, token: str) -> None:
    """Apaga a sessão. Sessão que já não existe não é erro."""
    conn.execute("DELETE FROM sessoes WHERE id = %s", (_id(token),))


def limpar_expiradas(conn: psycopg.Connection) -> int:
    return conn.execute("DELETE FROM sessoes WHERE expira_em <= now()").rowcount


def _id(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
