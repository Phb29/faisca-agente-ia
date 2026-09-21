"""Stream SSE de uma Conversa: LISTEN no canal da Conversa e repasse de cada Evento como
`event: <tipo>` / `data: <json dos dados>`. Ao conectar, reenvia a última mensagem gravada
do assistente como `message_done` com `reenvio: true`, para o front se recuperar depois
de uma queda."""

import json

from fastapi import APIRouter, Request
from sse_starlette import EventSourceResponse, ServerSentEvent

from ampere.api.cliente import conversa_do_cliente
from ampere.api.seguranca import ClienteId, Conexao, obter_config
from ampere.fila.eventos import Escuta
from ampere.fila.fila import ultima_mensagem_do_assistente

router = APIRouter()


@router.get("/conversas/{conversa_id}/stream")
async def stream(request: Request, conn: Conexao, cliente_id: ClienteId, conversa_id: str):
    conversa = conversa_do_cliente(conn, conversa_id, cliente_id)
    ultima = ultima_mensagem_do_assistente(conn, conversa["id"])
    config = obter_config(request)

    # O LISTEN é feito antes de responder: quando o front recebe os headers, nenhum
    # evento publicado dali em diante se perde.
    escuta = await Escuta(config.database_url, conversa["id"]).abrir()

    async def eventos():
        try:
            if ultima is not None:
                dados = {
                    "mensagem_id": ultima["id"],
                    "conteudo": ultima["conteudo"],
                    "reenvio": True,
                }
                yield ServerSentEvent(event="message_done", data=json.dumps(dados))
            async for evento in escuta:
                yield ServerSentEvent(event=evento.tipo, data=json.dumps(evento.dados))
        finally:
            await escuta.fechar()

    async def ao_desconectar(_mensagem) -> None:
        await escuta.fechar()

    return EventSourceResponse(eventos(), client_close_handler_callable=ao_desconectar)
