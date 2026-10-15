"""Eventos que viajam do worker para a API por LISTEN/NOTIFY, um canal por job (o da
Conversa, no chat), e da API para o front pelo SSE, com o mesmo nome e os mesmos dados.

No chat:

- `token` {texto}: um pedaço da resposta sendo escrita.
- `tool_call` {nome, args}: uma Ação começou.
- `etapa` {no, detalhe, alerta}: um nó do grafo terminou (os bastidores do turno).
- `approval_required` {aprovacao_id, pedido_id, valor, probabilidade, resumo, motivo_do_gate}.
- `message_done` {mensagem_id, conteudo, desfecho}: a resposta final, já gravada.

Na amostra ao vivo dos evals (ver `ampere.evals.ao_vivo`):

- `eval_inicio` {casos: [{id, texto, grupo}]}: os 3 sorteados, na ordem em que vão rodar.
- `eval_fase` {caso_id, fase}: uma fase de um caso começou.
- `eval_caso` {caso} ou {caso_id, grande}: um caso terminou, já gravado.
- `eval_fim` {resumo}: a amostra terminou, já gravada.

Nos dois: `error` {mensagem}.
"""

from collections.abc import AsyncIterator
from typing import Literal

import psycopg
from psycopg import sql
from pydantic import BaseModel, Field

from ampere.nucleo.banco import conectar_async

TipoDeEvento = Literal[
    "token",
    "tool_call",
    "etapa",
    "approval_required",
    "message_done",
    "error",
    "eval_inicio",
    "eval_fase",
    "eval_caso",
    "eval_fim",
]


class Evento(BaseModel):
    tipo: TipoDeEvento
    dados: dict = Field(default_factory=dict)


def canal(conversa_id: str) -> str:
    """Nome do canal do NOTIFY: `conversa_` mais o uuid sem hífens (identificador válido)."""
    return "conversa_" + str(conversa_id).replace("-", "")


def publicar(conn: psycopg.Connection, nome_do_canal: str, evento: Evento) -> None:
    """Envia o evento pelo canal. Em autocommit sai na hora; dentro de uma transação, só no
    commit."""
    conn.execute("SELECT pg_notify(%s, %s)", (nome_do_canal, evento.model_dump_json()))


class Escuta:
    """Um LISTEN num canal, numa conexão dedicada. `abrir` faz o LISTEN antes de qualquer
    consumo, para quem precisa garantir que nenhum evento se perca entre a resposta HTTP e
    o primeiro `async for` (o SSE)."""

    def __init__(self, conn_string: str, nome_do_canal: str) -> None:
        self._conn_string = conn_string
        self._canal = nome_do_canal
        self._conn: psycopg.AsyncConnection | None = None

    async def abrir(self) -> "Escuta":
        self._conn = await conectar_async(self._conn_string, autocommit=True)
        await self._conn.execute(sql.SQL("LISTEN {}").format(sql.Identifier(self._canal)))
        return self

    async def __aiter__(self) -> AsyncIterator[Evento]:
        assert self._conn is not None, "chame abrir() antes de iterar"
        async for notificacao in self._conn.notifies():
            yield Evento.model_validate_json(notificacao.payload)

    async def fechar(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


async def escutar(conn_string: str, nome_do_canal: str) -> AsyncIterator[Evento]:
    """Forma curta: abre, produz um Evento por notificação e fecha ao ser encerrado."""
    escuta = await Escuta(conn_string, nome_do_canal).abrir()
    try:
        async for evento in escuta:
            yield evento
    finally:
        await escuta.fechar()
