"""Limite de tentativas de login, contado no Postgres para valer igual com várias réplicas.

Numa janela de 15 minutos, cabem 5 falhas por IP e 20 por e-mail. O limite por IP segura
quem chuta muitas senhas de um lugar só; o por e-mail segura quem chuta a senha de uma conta
de muitos lugares, sem travar a conta para sempre. Só falhas contam, e o e-mail é sempre
normalizado (`strip().lower()`).
"""

from typing import Literal

import psycopg

JANELA_EM_MINUTOS = 15
FALHAS_POR_IP = 5
FALHAS_POR_EMAIL = 20


def normalizar(email: str) -> str:
    return email.strip().lower()


def registrar(conn: psycopg.Connection, email: str, ip: str, sucesso: bool) -> None:
    conn.execute(
        "INSERT INTO tentativas_de_login (email, ip, sucesso) VALUES (%s, %s, %s)",
        (normalizar(email), ip, sucesso),
    )


def bloqueio(conn: psycopg.Connection, email: str, ip: str) -> int | None:
    """Quantos segundos faltam para poder tentar de novo, ou None se pode agora."""
    esperas = [
        _espera(conn, "ip", ip, FALHAS_POR_IP),
        _espera(conn, "email", normalizar(email), FALHAS_POR_EMAIL),
    ]
    return max((s for s in esperas if s is not None), default=None)


def limpar_antigas(conn: psycopg.Connection) -> int:
    """Apaga as tentativas com mais de um dia: a janela é de minutos, o resto é só volume."""
    return conn.execute(
        "DELETE FROM tentativas_de_login WHERE momento < now() - interval '1 day'"
    ).rowcount


def _espera(
    conn: psycopg.Connection, coluna: Literal["ip", "email"], valor: str, maximo: int
) -> int | None:
    """Com `maximo` falhas na janela, libera quando a `maximo`-ésima mais recente sair dela,
    porque aí sobram `maximo - 1`. Com exatamente `maximo` falhas, é a mais antiga."""
    linha = conn.execute(
        "SELECT ceil(extract(epoch FROM "
        "momento + make_interval(mins => %(janela)s) - now()))::int AS segundos "
        f"FROM tentativas_de_login WHERE {coluna} = %(valor)s AND NOT sucesso "
        "AND momento > now() - make_interval(mins => %(janela)s) "
        "ORDER BY momento DESC OFFSET %(pular)s LIMIT 1",
        {"janela": JANELA_EM_MINUTOS, "valor": valor, "pular": maximo - 1},
    ).fetchone()
    return max(linha["segundos"], 1) if linha else None
