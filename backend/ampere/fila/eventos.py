"""Eventos que viajam do worker para a API por LISTEN/NOTIFY, um canal por Conversa.

Cinco tipos, os mesmos que o SSE repassa ao front: `token`, `tool_call`,
`approval_required`, `message_done` e `error`.
"""

from collections.abc import AsyncIterator
from typing import Literal

import psycopg
from pydantic import BaseModel, Field

from ampere.nucleo.banco import conectar_async

TipoDeEvento = Literal["token", "tool_call", "approval_required", "message_done", "error"]


class Evento(BaseModel):
    tipo: TipoDeEvento
    dados: dict = Field(default_factory=dict)


def canal(conversa_id: str) -> str:
    """Nome do canal do NOTIFY: `conversa_` mais o uuid sem hifens (identificador válido)."""
    return "conversa_" + str(conversa_id).replace("-", "")


def publicar(conn: psycopg.Connection, conversa_id: str, evento: Evento) -> None:
    """Envia o evento pelo canal da Conversa. A conexão precisa estar em autocommit ou
    commitar depois, senão o NOTIFY fica preso na transação."""
    conn.execute("SELECT pg_notify(%s, %s)", (canal(conversa_id), evento.model_dump_json()))


async def escutar(conn_string: str, conversa_id: str) -> AsyncIterator[Evento]:
    """Abre uma conexão assíncrona só para o LISTEN e produz um Evento por notificação.
    Fechar o gerador (`aclose`) encerra a conexão."""
    conn = await conectar_async(conn_string, autocommit=True)
    try:
        await conn.execute(f"LISTEN {canal(conversa_id)}")
        async for notificacao in conn.notifies():
            yield Evento.model_validate_json(notificacao.payload)
    finally:
        await conn.close()
