"""O worker: reserva um job, roda o executor e publica cada evento no canal do job.

A mensagem final e a Aprovação Pendente são gravadas ANTES do NOTIFY, para que quem receber
o evento já encontre o dado no banco. Sem job, o worker dorme em `LISTEN fila_de_jobs` e
acorda assim que a API enfileira algo (ou a cada `intervalo`, por garantia).
"""

import logging
import threading
import traceback

import psycopg

from ampere.acoes.aprovacoes import criar_aprovacao
from ampere.conversas.conversas import StatusDaConversa, atualizar_status, gravar_mensagem
from ampere.fila.eventos import Evento, publicar
from ampere.fila.executor import Executor
from ampere.fila.fila import CANAL_DA_FILA, Job, concluir_job, pegar_proximo_job
from ampere.nucleo.banco import conectar

log = logging.getLogger(__name__)

STATUS_POR_DESFECHO: dict[str | None, StatusDaConversa] = {
    "Resolvida": "resolvida",
    "Escalada": "escalada",
}


def processar_um_job(conn: psycopg.Connection, executor: Executor) -> bool:
    """Processa no máximo um job numa conexão em autocommit. False quando a fila está vazia."""
    job = pegar_proximo_job(conn)
    if job is None:
        return False
    onde = f"da Conversa {job.conversa_id}" if job.conversa_id else f"no canal {job.canal}"
    log.info("job %s (%s) %s", job.id, job.tipo, onde)
    try:
        for evento in executor.executar(job):
            publicar(conn, job.canal, _persistir(conn, job, evento))
    except Exception as exc:  # noqa: BLE001 - qualquer falha vira erro do job, não do worker
        erro = "".join(traceback.format_exception_only(exc)).strip()
        log.exception("job %s falhou", job.id)
        concluir_job(conn, job.id, erro=erro)
        publicar(conn, job.canal, Evento(tipo="error", dados={"mensagem": erro}))
    else:
        concluir_job(conn, job.id)
    return True


def rodar_worker(
    conn_string: str,
    executor: Executor,
    *,
    uma_vez: bool = False,
    intervalo: float = 5.0,
    parar: threading.Event | None = None,
) -> None:
    """Loop do worker. Com `uma_vez`, esvazia a fila e volta; com `parar`, encerra assim que
    o evento for sinalizado (no máximo `intervalo` segundos depois)."""
    with conectar(conn_string, autocommit=True) as conn:
        conn.execute(f"LISTEN {CANAL_DA_FILA}")
        while parar is None or not parar.is_set():
            if processar_um_job(conn, executor):
                continue
            if uma_vez:
                return
            for _ in conn.notifies(timeout=intervalo, stop_after=1):
                pass


def _persistir(conn: psycopg.Connection, job: Job, evento: Evento) -> Evento:
    """Grava o que o evento exige e devolve o evento pronto para publicar."""
    dados = evento.dados
    if evento.tipo == "approval_required":
        with conn.transaction():
            aprovacao_id = criar_aprovacao(
                conn,
                conversa_id=job.conversa_id,
                cliente_id=job.payload.get("cliente_id", ""),
                pedido_id=dados["pedido_id"],
                valor=dados["valor"],
                probabilidade=dados["probabilidade"],
                resumo=dados["resumo"],
                motivo_do_gate=dados.get("motivo_do_gate"),
            )
            atualizar_status(conn, job.conversa_id, "aprovacao_pendente")
        return evento.model_copy(update={"dados": {**dados, "aprovacao_id": aprovacao_id}})
    if evento.tipo == "message_done":
        with conn.transaction():
            mensagem_id = gravar_mensagem(conn, job.conversa_id, "assistente", dados["conteudo"])
            status = STATUS_POR_DESFECHO.get(dados.get("desfecho"), "aberta")
            atualizar_status(conn, job.conversa_id, status)
        return evento.model_copy(update={"dados": {**dados, "mensagem_id": mensagem_id}})
    return evento
