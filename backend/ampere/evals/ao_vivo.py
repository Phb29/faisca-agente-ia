"""A amostra ao vivo (ver docs/adr/0009): o job `eval` da fila sorteia 3 casos, roda um de
cada vez e conta cada passo por eventos, sempre gravando antes de avisar.

A fila não sabe que isto existe: a raiz de composição liga o tipo de job `eval` a este
executor. Um caso que falha vira um caso com `erro`, e a amostra segue; uma falha fora dos
casos marca a execução como erro e sobe para o worker, que publica `error`. Se uma escrita
não valer, a execução foi liberada como abandonada: antes de começar, o executor avisa com
`error`; no meio, ele só para, porque a liberação já avisou a tela.
"""

import logging
import random
import time
import traceback
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass, field
from typing import Protocol

from langchain_core.language_models import BaseChatModel

from ampere.evals import agente, calibracao, rag
from ampere.evals.agente import Composicao, ExecutorDeCenarios
from ampere.evals.execucoes import RegistroDeExecucoes
from ampere.evals.relatorio import PassosDoCaso, Sorteado, caso_com_erro, contexto_base
from ampere.fila.eventos import Evento
from ampere.fila.fila import Job
from ampere.nucleo.config import Config
from ampere.rag.busca import Retriever

log = logging.getLogger(__name__)

# O NOTIFY aceita até 8.000 bytes: um caso maior vai só com o id, e a tela relê a execução.
LIMITE_DO_AVISO = 7000


class ComposicaoAoVivo(Composicao, Protocol):
    """A composição do eval do agente mais o que a Busca usa: o retriever e o gerador do ar."""

    retriever: Retriever

    def gerador(self) -> BaseChatModel: ...


@dataclass(frozen=True)
class RoteiroDoEval:
    """O que muda de um eval para outro numa amostra."""

    sortear: Callable[[random.Random], list[Sorteado]]
    passos: Callable[[Sorteado], PassosDoCaso]
    prompts: tuple[str, ...]
    resumo: Callable[[list[dict]], dict]
    # O que só este eval registra no contexto (a variante da Busca, a seed do Juiz).
    contexto: dict = field(default_factory=dict)


class ExecutorDeAvaliacao:
    """O `Executor` do job `eval`: sorteia a amostra, roda um caso de cada vez e grava cada
    passo antes de avisar (ver docstring do módulo)."""

    def __init__(
        self,
        config: Config,
        composicao: ComposicaoAoVivo,
        registro: RegistroDeExecucoes,
        *,
        sorteio: Callable[[], random.Random] = random.Random,
    ) -> None:
        self.config = config
        self.composicao = composicao
        self.registro = registro
        self._sorteio = sorteio
        self._cenarios: ExecutorDeCenarios | None = None

    def executar(self, job: Job) -> Iterator[Evento]:
        execucao_id = job.payload["execucao_id"]
        try:
            yield from self._executar(execucao_id, job.payload["eval"])
        except Exception as exc:
            self.registro.falhar(execucao_id, _mensagem(exc))
            raise

    def _executar(self, execucao_id: str, eval: str) -> Iterator[Evento]:
        roteiro = self._roteiro(eval)
        sorteados = roteiro.sortear(self._sorteio())
        cartoes = [s.cartao() for s in sorteados]
        contexto = {
            **contexto_base(self.config, prompts=roteiro.prompts, n=len(sorteados)),
            **roteiro.contexto,
            "sorteados": cartoes,
        }
        if not self.registro.marcar_rodando(execucao_id, contexto):
            yield Evento(tipo="error", dados={"mensagem": "amostra liberada antes de começar"})
            return
        yield Evento(tipo="eval_inicio", dados={"casos": cartoes})

        casos: list[dict] = []
        for sorteado in sorteados:
            inicio = time.perf_counter()
            try:
                caso = yield from _em_eventos(sorteado.id, roteiro.passos(sorteado))
            except Exception as exc:  # noqa: BLE001 - um caso que falha não derruba a amostra
                log.exception("caso %s da amostra %s falhou", sorteado.id, execucao_id)
                caso = caso_com_erro(sorteado, _mensagem(exc), time.perf_counter() - inicio)
            if not self.registro.anexar_caso(execucao_id, caso):
                return
            casos.append(caso)
            yield evento_do_caso(caso)

        resumo = roteiro.resumo(casos)
        if self.registro.concluir(execucao_id, resumo):
            yield Evento(tipo="eval_fim", dados={"resumo": resumo})

    def _roteiro(self, eval: str) -> RoteiroDoEval:
        if eval == "rag":
            variante = rag.variante_configurada(self.config).nome
            return RoteiroDoEval(
                sortear=rag.sortear_amostra,
                passos=lambda s: rag.caso_ao_vivo(
                    s,
                    retriever=self.composicao.retriever,
                    gerador=self.composicao.gerador(),
                    juiz=self.composicao.juiz(),
                ),
                prompts=rag.PROMPTS_DO_RAG,
                resumo=lambda casos: rag.resumo_rag(variante, casos, []),
                contexto={"variante": variante},
            )
        if eval == "agente":
            cenarios = self._executor_de_cenarios()
            return RoteiroDoEval(
                sortear=agente.sortear_amostra,
                passos=lambda s: agente.caso_ao_vivo(s, cenarios),
                prompts=agente.PROMPTS_DO_AGENTE,
                resumo=agente.resumo_agente,
            )
        if eval == "juiz":
            exemplos = calibracao.few_shot_do_treino()
            return RoteiroDoEval(
                sortear=calibracao.sortear_amostra,
                passos=lambda s: calibracao.caso_ao_vivo(
                    s, juiz=self.composicao.juiz(), few_shot=exemplos
                ),
                prompts=calibracao.PROMPTS_DO_JUIZ,
                resumo=calibracao.resumo_amostra_juiz,
                contexto={"seed": calibracao.SEED_DA_AMOSTRA},
            )
        raise ValueError(f"eval desconhecido: {eval!r}")

    def _executor_de_cenarios(self) -> ExecutorDeCenarios:
        """Um só por processo: reaproveita a composição do grafo entre as amostras. O
        embedder que ele cria é instância nova, mas carrega o mesmo MiniLM do processo."""
        if self._cenarios is None:
            self._cenarios = ExecutorDeCenarios(self.config, self.composicao)
        return self._cenarios


def _em_eventos(caso_id: str, passos: PassosDoCaso) -> Generator[Evento, None, dict]:
    """Cada fase do caso vira um `eval_fase`; o caso pronto é o valor de retorno."""
    while True:
        try:
            fase = next(passos)
        except StopIteration as fim:
            return fim.value
        yield Evento(tipo="eval_fase", dados={"caso_id": caso_id, "fase": fase})


def evento_do_caso(caso: dict) -> Evento:
    evento = Evento(tipo="eval_caso", dados={"caso": caso})
    if len(evento.model_dump_json().encode()) > LIMITE_DO_AVISO:
        return Evento(tipo="eval_caso", dados={"caso_id": caso["id"], "grande": True})
    return evento


def _mensagem(exc: Exception) -> str:
    return "".join(traceback.format_exception_only(exc)).strip()
