"""O worker: pega um job da fila, roda o executor e publica cada evento no canal da
Conversa. Grava a mensagem final e a Aprovação Pendente ANTES de publicar, para que quem
receber o evento já encontre o dado no banco."""

import importlib
import threading
import time
import traceback

from ampere.fila.eventos import Evento, publicar
from ampere.fila.executor import Executor
from ampere.fila.fila import (
    Job,
    atualizar_status_conversa,
    concluir_job,
    criar_aprovacao,
    gravar_mensagem,
    pegar_proximo_job,
)
from ampere.nucleo.banco import conectar


def _tratar_evento(conn, job: Job, evento: Evento) -> Evento:
    """Persiste o que o evento exige e devolve o evento pronto para publicar."""
    if evento.tipo == "approval_required":
        d = evento.dados
        aprovacao_id = criar_aprovacao(
            conn,
            job.conversa_id,
            job.payload.get("cliente_id", ""),
            d["pedido_id"],
            d["valor"],
            d["probabilidade"],
            d["resumo"],
        )
        atualizar_status_conversa(conn, job.conversa_id, "aprovacao_pendente")
        return Evento(tipo=evento.tipo, dados={**d, "aprovacao_id": aprovacao_id})
    if evento.tipo == "message_done":
        mensagem_id = gravar_mensagem(conn, job.conversa_id, "assistente", evento.dados["conteudo"])
        status = "escalada" if evento.dados.get("desfecho") == "Escalada" else "aberta"
        atualizar_status_conversa(conn, job.conversa_id, status)
        return Evento(tipo=evento.tipo, dados={**evento.dados, "mensagem_id": mensagem_id})
    return evento


def processar_um_job(conn_string: str, executor: Executor) -> bool:
    """Processa no máximo um job. Devolve False quando a fila está vazia."""
    with conectar(conn_string, autocommit=True) as conn:
        job = pegar_proximo_job(conn)
        if job is None:
            return False
        try:
            for evento in executor.executar(job):
                publicar(conn, job.conversa_id, _tratar_evento(conn, job, evento))
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira erro do job
            erro = "".join(traceback.format_exception_only(exc)).strip()
            concluir_job(conn, job.id, erro=erro)
            publicar(conn, job.conversa_id, Evento(tipo="error", dados={"mensagem": erro}))
        else:
            concluir_job(conn, job.id)
        return True


def rodar_worker(
    conn_string: str,
    executor: Executor,
    *,
    uma_vez: bool = False,
    intervalo: float = 0.5,
    parar: threading.Event | None = None,
) -> None:
    """Loop do worker. Com `uma_vez`, processa até esvaziar a fila e volta. Com `parar`,
    encerra assim que o evento for sinalizado."""
    while parar is None or not parar.is_set():
        processou = processar_um_job(conn_string, executor)
        if processou:
            continue
        if uma_vez:
            return
        if parar is not None:
            parar.wait(intervalo)
        else:
            time.sleep(intervalo)


def main() -> None:
    """Ponto de entrada `python -m ampere.fila.worker`: delega à raiz de composição (`ampere.cli`),
    que é quem monta o grafo e o `ExecutorDoGrafo`. Importa por nome para esta pasta não
    depender do grafo (ver docs/adr/0005)."""
    from ampere.nucleo.config import config

    cli = importlib.import_module("ampere.cli")
    rodar_worker(config().database_url, cli.montar_executor(config()))


if __name__ == "__main__":
    main()
