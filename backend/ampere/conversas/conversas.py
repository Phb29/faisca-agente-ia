"""Conversas e o transcript de mensagens que o chat e a Tela do Atendente mostram.

É o registro legível da Conversa, separado da Memória de Curto Prazo (o estado do grafo no
checkpointer): aqui fica só o que o Cliente disse e o que o chatbot respondeu. As funções
recebem a conexão e não abrem transação; quem precisa de atomicidade abre a sua.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import psycopg
from psycopg.rows import class_row

StatusDaConversa = Literal["aberta", "aprovacao_pendente", "escalada", "resolvida"]
Papel = Literal["cliente", "assistente"]
TAMANHO_DO_TITULO = 60


@dataclass(frozen=True)
class Conversa:
    id: str
    cliente_id: str
    titulo: str | None
    status: StatusDaConversa
    criada_em: datetime
    atualizada_em: datetime


@dataclass(frozen=True)
class Mensagem:
    id: str
    conversa_id: str
    papel: Papel
    conteudo: str
    message_id: str | None
    criada_em: datetime


SELECT_CONVERSA = (
    "SELECT id::text, cliente_id, titulo, status, criada_em, atualizada_em FROM conversas"
)
SELECT_MENSAGEM = (
    "SELECT id::text, conversa_id::text, papel, conteudo, message_id, criada_em FROM mensagens"
)


def criar_conversa(conn: psycopg.Connection, cliente_id: str, titulo: str | None = None) -> str:
    linha = conn.execute(
        "INSERT INTO conversas (cliente_id, titulo) VALUES (%s, %s) RETURNING id::text",
        (cliente_id, titulo),
    ).fetchone()
    return linha["id"]


def listar_conversas(conn: psycopg.Connection, cliente_id: str) -> list[Conversa]:
    with conn.cursor(row_factory=class_row(Conversa)) as cur:
        sql = f"{SELECT_CONVERSA} WHERE cliente_id = %s ORDER BY atualizada_em DESC"
        return cur.execute(sql, (cliente_id,)).fetchall()


def obter_conversa(conn: psycopg.Connection, conversa_id: str) -> Conversa | None:
    with conn.cursor(row_factory=class_row(Conversa)) as cur:
        return cur.execute(f"{SELECT_CONVERSA} WHERE id = %s", (conversa_id,)).fetchone()


def atualizar_status(
    conn: psycopg.Connection,
    conversa_id: str,
    status: StatusDaConversa,
    *,
    titulo_se_vazio: str | None = None,
) -> None:
    conn.execute(
        "UPDATE conversas SET status = %s, titulo = COALESCE(titulo, %s), atualizada_em = now() "
        "WHERE id = %s",
        (status, titulo_se_vazio, conversa_id),
    )


def gravar_mensagem(
    conn: psycopg.Connection,
    conversa_id: str,
    papel: Papel,
    conteudo: str,
    message_id: str | None = None,
) -> str | None:
    """Devolve o id da mensagem gravada, ou None se o `message_id` já existia (reenvio)."""
    linha = conn.execute(
        "INSERT INTO mensagens (conversa_id, papel, conteudo, message_id) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING RETURNING id::text",
        (conversa_id, papel, conteudo, message_id),
    ).fetchone()
    return linha["id"] if linha else None


def listar_mensagens(conn: psycopg.Connection, conversa_id: str) -> list[Mensagem]:
    with conn.cursor(row_factory=class_row(Mensagem)) as cur:
        sql = f"{SELECT_MENSAGEM} WHERE conversa_id = %s ORDER BY criada_em, id"
        return cur.execute(sql, (conversa_id,)).fetchall()


def ultima_mensagem_do_assistente(conn: psycopg.Connection, conversa_id: str) -> Mensagem | None:
    with conn.cursor(row_factory=class_row(Mensagem)) as cur:
        sql = (
            f"{SELECT_MENSAGEM} WHERE conversa_id = %s AND papel = 'assistente' "
            "ORDER BY criada_em DESC, id DESC LIMIT 1"
        )
        return cur.execute(sql, (conversa_id,)).fetchone()


def titulo_a_partir_de(texto: str) -> str:
    """Primeira linha da mensagem, cortada numa palavra inteira com reticências."""
    linha = " ".join(texto.strip().splitlines()[0].split()) if texto.strip() else ""
    if len(linha) <= TAMANHO_DO_TITULO:
        return linha
    return linha[:TAMANHO_DO_TITULO].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
