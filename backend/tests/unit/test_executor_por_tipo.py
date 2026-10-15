"""A fila roda trabalhos diferentes sem conhecer nenhum: cada tipo de job tem o seu executor."""

import pytest

from ampere.fila.eventos import Evento
from ampere.fila.executor import ExecutorFalso, ExecutorPorTipo
from ampere.fila.fila import Job


def job(tipo: str) -> Job:
    return Job(id=1, tipo=tipo, conversa_id=None, message_id=None, payload={}, canal="c")


def test_repassa_cada_job_ao_executor_do_tipo_dele():
    chat = ExecutorFalso([Evento(tipo="message_done", dados={"conteudo": "oi"})])
    avaliacao = ExecutorFalso([Evento(tipo="eval_fim", dados={"resumo": {}})])
    executor = ExecutorPorTipo({"mensagem": chat, "retomada": chat, "eval": avaliacao})

    assert [e.tipo for e in executor.executar(job("eval"))] == ["eval_fim"]
    assert [e.tipo for e in executor.executar(job("mensagem"))] == ["message_done"]
    assert [e.tipo for e in executor.executar(job("retomada"))] == ["message_done"]
    assert len(avaliacao.jobs) == 1
    assert len(chat.jobs) == 2


def test_tipo_sem_executor_e_erro_do_job():
    executor = ExecutorPorTipo({"mensagem": ExecutorFalso([])})

    with pytest.raises(ValueError, match="eval"):
        list(executor.executar(job("eval")))
