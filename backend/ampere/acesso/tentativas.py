"""Limite de tentativas de login, contado no Postgres para valer igual com várias réplicas.

Numa janela de 15 minutos, cabem 5 falhas por IP e 20 por e-mail. O limite por IP segura
quem chuta muitas senhas de um lugar só; o por e-mail segura quem chuta a senha de uma conta
de muitos lugares, sem travar a conta para sempre. Só falhas contam, e o e-mail é sempre
normalizado (`strip().lower()`).

O limite por e-mail não vale para o IP de onde a conta entrou com sucesso nos últimos 30 dias.
Sem isso, qualquer um trancaria o dono para fora por 15 minutos com 20 chutes de onde
quisesse. Por isso os sucessos ficam guardados 30 dias, e as falhas, só um.

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
DIAS_DE_CONFIANCA = 30


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
    esperas = [_espera(conn, "ip", ip, FALHAS_POR_IP, tentativa)]
    if not _ip_de_confianca(conn, email, ip):
        esperas.append(_espera(conn, "email", email, FALHAS_POR_EMAIL, tentativa))
    espera = max((s for s in esperas if s is not None), default=None)
    if espera is not None:
        conn.execute("DELETE FROM tentativas_de_login WHERE id = %s", (tentativa,))
        raise Bloqueado(espera)
    return tentativa


def marcar_sucesso(conn: psycopg.Connection, tentativa: int) -> None:
    conn.execute("UPDATE tentativas_de_login SET sucesso = true WHERE id = %s", (tentativa,))


def limpar_antigas(conn: psycopg.Connection) -> int:
    """Apaga as falhas com mais de um dia (a janela é de minutos, o resto é só volume) e os
    sucessos com mais de 30 dias (eles só servem para reconhecer o IP de quem já entrou)."""
    return conn.execute(
        "DELETE FROM tentativas_de_login WHERE momento < now() - "
        "CASE WHEN sucesso THEN make_interval(days => %s) ELSE interval '1 day' END",
        (DIAS_DE_CONFIANCA,),
    ).rowcount


def _ip_de_confianca(conn: psycopg.Connection, email: str, ip: str) -> bool:
    """Se a conta já entrou com sucesso deste IP nos últimos `DIAS_DE_CONFIANCA` dias."""
    return conn.execute(
        "SELECT EXISTS (SELECT 1 FROM tentativas_de_login WHERE email = %s AND ip = %s "
        "AND sucesso AND momento > now() - make_interval(days => %s)) AS confia",
        (email, ip, DIAS_DE_CONFIANCA),
    ).fetchone()["confia"]


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
