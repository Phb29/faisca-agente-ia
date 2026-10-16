"""Rotas da Tela de Avaliação, protegidas pela sessão de login, como a Central: as execuções
de cada eval, a amostra em andamento, o disparo de uma amostra ao vivo (um job `eval` na
mesma fila do chat) e o stream dela (ver docs/adr/0009).

As rotas de leitura liberam antes as amostras abandonadas, para a tela nunca mostrar uma
rodada morta como em andamento.
"""

import json

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg_pool import ConnectionPool
from sse_starlette import EventSourceResponse, ServerSentEvent
from starlette.concurrency import run_in_threadpool

from ampere.api.dependencias import Conexao, Configuracao, Pool, exigir_sessao, uuid_ou_404
from ampere.evals.execucoes import (
    EVALS,
    amostra_em_andamento,
    canal_da_execucao,
    criar_amostra,
    liberar_abandonadas,
    listar,
    obter,
)
from ampere.fila.eventos import Escuta
from ampere.fila.fila import enfileirar_sem_conversa

router = APIRouter(prefix="/avaliacao", dependencies=[Depends(exigir_sessao)])

FIM_DO_STREAM = {"eval_fim", "error"}
TERMINADAS = {"concluida", "erro"}


def _eval_ou_404(eval: str) -> str:
    if eval not in EVALS:
        raise HTTPException(status_code=404, detail="eval desconhecido")
    return eval


@router.get("/amostra")
def amostra_atual(conn: Conexao):
    """A amostra pendente ou rodando, de qualquer eval, sem os casos, ou `null`."""
    liberar_abandonadas(conn)
    return amostra_em_andamento(conn)


@router.get("/execucoes/{execucao_id}")
def ler_execucao(execucao_id: str, conn: Conexao):
    execucao = obter(conn, uuid_ou_404(execucao_id))
    if execucao is None:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    return execucao


def _ler(pool: ConnectionPool, execucao_id: str):
    with pool.connection() as conn:
        return obter(conn, execucao_id)


@router.get("/execucoes/{execucao_id}/stream")
async def stream(execucao_id: str, config: Configuracao, pool: Pool):
    """Primeiro o LISTEN, depois a foto da execução (`eval_estado`), depois os eventos do
    canal: nada publicado depois da foto se perde, e um F5 no meio da amostra repõe os casos
    já prontos (a tela descarta caso repetido pelo id). Execução terminada manda só a foto."""
    execucao_id = uuid_ou_404(execucao_id)
    escuta = await Escuta(config.database_url, canal_da_execucao(execucao_id)).abrir()
    try:
        execucao = await run_in_threadpool(_ler, pool, execucao_id)
    except Exception:
        await escuta.fechar()
        raise
    if execucao is None:
        await escuta.fechar()
        raise HTTPException(status_code=404, detail="Execução não encontrada")

    async def eventos():
        try:
            foto = json.dumps(jsonable_encoder(execucao))
            yield ServerSentEvent(event="eval_estado", data=foto)
            if execucao["status"] in TERMINADAS:
                return
            async for evento in escuta:
                yield ServerSentEvent(event=evento.tipo, data=json.dumps(evento.dados))
                if evento.tipo in FIM_DO_STREAM:
                    return
        finally:
            await escuta.fechar()

    async def ao_desconectar(_mensagem) -> None:
        await escuta.fechar()

    return EventSourceResponse(eventos(), client_close_handler_callable=ao_desconectar)


@router.get("/{eval}/execucoes")
def listar_execucoes(eval: str, conn: Conexao, limite: int = Query(20, ge=1, le=100)):
    """As execuções do eval, mais novas primeiro, sem os casos."""
    _eval_ou_404(eval)
    liberar_abandonadas(conn)
    return listar(conn, eval, limite=limite)


@router.post("/{eval}/amostra", status_code=202)
def rodar_amostra(eval: str, conn: Conexao):
    """Libera abandonadas, cria a amostra e enfileira o job numa transação só. Se já houver
    uma em andamento, de qualquer eval, desfaz tudo e responde 409 com o id e o eval dela,
    para a tela se conectar à que já roda."""
    _eval_ou_404(eval)
    try:
        with conn.transaction():
            liberar_abandonadas(conn)
            execucao_id = criar_amostra(conn, eval)
            enfileirar_sem_conversa(
                conn,
                tipo="eval",
                canal=canal_da_execucao(execucao_id),
                payload={"execucao_id": execucao_id, "eval": eval},
            )
    except psycopg.errors.UniqueViolation:
        atual = amostra_em_andamento(conn)
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Já existe uma amostra rodando.",
                "execucao_id": atual["id"] if atual else None,
                "eval": atual["eval"] if atual else None,
            },
        )
    return {"execucao_id": execucao_id}
