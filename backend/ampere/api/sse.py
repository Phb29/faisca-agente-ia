"""Stream SSE de uma Conversa: LISTEN no canal da Conversa e repasse de cada Evento como
`event: <tipo>` / `data: <json dos dados>`.

Ao conectar, reenvia a última resposta gravada como `message_done` com `reenvio: true`: é
assim que o front se recupera de uma queda sem perder a resposta. A conexão do pool é usada
só para essa leitura inicial e devolvida na hora; o LISTEN tem conexão própria, que dura
enquanto o navegador estiver ouvindo.
"""

import json

from fastapi import APIRouter
from psycopg_pool import ConnectionPool
from sse_starlette import EventSourceResponse, ServerSentEvent
from starlette.concurrency import run_in_threadpool

from ampere.api.cliente import conversa_do_cliente
from ampere.api.dependencias import ClienteId, Configuracao, Pool
from ampere.conversas.conversas import Mensagem, ultima_mensagem_do_assistente
from ampere.fila.eventos import Escuta, canal

router = APIRouter()


def _estado_inicial(
    pool: ConnectionPool, conversa_id: str, cliente_id: str
) -> tuple[str, Mensagem | None]:
    with pool.connection() as conn:
        conversa = conversa_do_cliente(conn, conversa_id, cliente_id)
        return conversa.id, ultima_mensagem_do_assistente(conn, conversa.id)


@router.get("/conversas/{conversa_id}/stream")
async def stream(config: Configuracao, pool: Pool, cliente_id: ClienteId, conversa_id: str):
    conversa_id, ultima = await run_in_threadpool(_estado_inicial, pool, conversa_id, cliente_id)

    # O LISTEN acontece antes da resposta: quando o front recebe os headers, nenhum evento
    # publicado dali em diante se perde.
    escuta = await Escuta(config.database_url, canal(conversa_id)).abrir()

    async def eventos():
        try:
            if ultima is not None:
                reenvio = {"mensagem_id": ultima.id, "conteudo": ultima.conteudo, "reenvio": True}
                yield ServerSentEvent(event="message_done", data=json.dumps(reenvio))
            async for evento in escuta:
                yield ServerSentEvent(event=evento.tipo, data=json.dumps(evento.dados))
        finally:
            await escuta.fechar()

    async def ao_desconectar(_mensagem) -> None:
        await escuta.fechar()

    return EventSourceResponse(eventos(), client_close_handler_callable=ao_desconectar)
