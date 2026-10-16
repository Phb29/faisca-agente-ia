"""Limite de tentativas de login, contado no Postgres para valer igual com várias réplicas.

Numa janela de 15 minutos, cabem 5 falhas por IP e 20 por e-mail. O limite por IP segura
quem chuta muitas senhas de um lugar só; o por e-mail segura quem chuta a senha de uma conta
de muitos lugares, sem travar a conta para sempre. Só falhas contam, e o e-mail é sempre
normalizado (`strip().lower()`).

Toda tentativa entra no banco como falha antes de a senha ser conferida (`comecar`), e só vira
sucesso depois, se a senha bater (`marcar_sucesso`). A conexão precisa estar em autocommit,
como as do pool: cada tentativa fica visível na hora para as outras que correm junto, e uma
rajada não consegue conferir mais senhas do que o limite.
"""

from typing import Literal

import psycopg

JANELA_EM_MINUTOS = 15
FALHAS_POR_IP = 5
FALHAS_POR_EMAIL = 20


class Bloqueado(Exception):
    """Tentativas demais na janela. `segundos` é quanto falta para poder tentar de novo."""

    def __init__(self, segundos: int):
        super().__init__(f"tentativas demais; de novo em {segundos} s")
        self.segundos = segundos


def normalizar(email: str) -> str:
    return email.strip().lower()


def comecar(conn: psycopg.Connection, email: str, ip: str) -> int:
    """Registra a tentativa como falha e só então conta a janela, já com ela. Se ela passa do
    limite, apaga a tentativa (o 429 não deixa rastro) e levanta `Bloqueado`. Senão, devolve o
    id dela, para `marcar_sucesso` se a senha bater."""
    email = normalizar(email)
    tentativa = conn.execute(
        "INSERT INTO tentativas_de_login (email, ip, sucesso) VALUES (%s, %s, false) RETURNING id",
        (email, ip),
    ).fetchone()["id"]
    esperas = [
        _espera(conn, "ip", ip, FALHAS_POR_IP, tentativa),
        _espera(conn, "email", email, FALHAS_POR_EMAIL, tentativa),
    ]
    espera = max((s for s in esperas if s is not None), default=None)
    if espera is not None:
        conn.execute("DELETE FROM tentativas_de_login WHERE id = %s", (tentativa,))
        raise Bloqueado(espera)
    return tentativa


def marcar_sucesso(conn: psycopg.Connection, tentativa: int) -> None:
    conn.execute("UPDATE tentativas_de_login SET sucesso = true WHERE id = %s", (tentativa,))


def limpar_antigas(conn: psycopg.Connection) -> int:
    """Apaga as tentativas com mais de um dia: a janela é de minutos, o resto é só volume."""
    return conn.execute(
        "DELETE FROM tentativas_de_login WHERE momento < now() - interval '1 day'"
    ).rowcount


def _espera(
    conn: psycopg.Connection,
    coluna: Literal["ip", "email"],
    valor: str,
    maximo: int,
    propria: int,
) -> int | None:
    """Conta as falhas da janela além da tentativa `propria`. Com `maximo` delas, a própria
    passaria do limite; libera quando a `maximo`-ésima mais recente sair da janela, porque aí
    sobram `maximo - 1` e a próxima cabe."""
    linha = conn.execute(
        "SELECT ceil(extract(epoch FROM "
        "momento + make_interval(mins => %(janela)s) - now()))::int AS segundos "
        f"FROM tentativas_de_login WHERE {coluna} = %(valor)s AND NOT sucesso "
        "AND id <> %(propria)s AND momento > now() - make_interval(mins => %(janela)s) "
        "ORDER BY momento DESC OFFSET %(pular)s LIMIT 1",
        {"janela": JANELA_EM_MINUTOS, "valor": valor, "propria": propria, "pular": maximo - 1},
    ).fetchone()
    return max(linha["segundos"], 1) if linha else None
