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


class Escuta:
    """Um LISTEN no canal da Conversa. `abrir` executa o LISTEN antes de qualquer consumo,
    para quem precisa garantir que nenhum evento se perca entre a resposta e o primeiro
    `async for` (o SSE); `fechar` encerra a conexão."""

    def __init__(self, conn_string: str, conversa_id: str) -> None:
        self._conn_string = conn_string
        self._canal = canal(conversa_id)
        self._conn: psycopg.AsyncConnection | None = None

    async def abrir(self) -> "Escuta":
        self._conn = await conectar_async(self._conn_string, autocommit=True)
        await self._conn.execute(f"LISTEN {self._canal}")
        return self

    async def __aiter__(self) -> AsyncIterator[Evento]:
        assert self._conn is not None, "chame abrir() antes de iterar"
        async for notificacao in self._conn.notifies():
            yield Evento.model_validate_json(notificacao.payload)

    async def fechar(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


async def escutar(conn_string: str, conversa_id: str) -> AsyncIterator[Evento]:
    """Forma curta: abre, produz um Evento por notificação e fecha ao ser encerrado."""
    escuta = await Escuta(conn_string, conversa_id).abrir()
    try:
        async for evento in escuta:
            yield evento
    finally:
        await escuta.fechar()
