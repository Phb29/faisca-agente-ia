"""Quem executa um job. O worker só conhece este Protocol; os executores de verdade (o do
grafo, em `ampere.grafo.executor`, e o da amostra ao vivo, em `ampere.evals.ao_vivo`) são
ligados a cada tipo de job pela raiz de composição (`ampere/composicao.py`), com o
`ExecutorPorTipo`. Assim a fila não sabe nada do grafo nem dos evals.

Os dados de cada evento seguem a convenção de `ampere.fila.eventos`.
"""

from collections.abc import Callable, Iterator, Mapping
from typing import Protocol

from ampere.fila.eventos import Evento
from ampere.fila.fila import Job


class Executor(Protocol):
    def executar(self, job: Job) -> Iterator[Evento]: ...


class ExecutorPorTipo:
    """Repassa cada job ao executor do tipo dele. Tipo sem executor é erro do job (o worker
    marca o job e publica `error`), não do worker."""

    def __init__(self, executores: Mapping[str, Executor]) -> None:
        self._executores = dict(executores)

    def executar(self, job: Job) -> Iterator[Evento]:
        executor = self._executores.get(job.tipo)
        if executor is None:
            raise ValueError(f"nenhum executor para jobs do tipo {job.tipo!r}")
        yield from executor.executar(job)


class ExecutorFalso:
    """Emite uma lista fixa de eventos, ou a lista que uma função devolve para o job.
    Guarda em `jobs` os jobs recebidos, para asserções."""

    def __init__(self, eventos: list[Evento] | Callable[[Job], list[Evento]]) -> None:
        self._eventos = eventos
        self.jobs: list[Job] = []

    def executar(self, job: Job) -> Iterator[Evento]:
        self.jobs.append(job)
        eventos = self._eventos(job) if callable(self._eventos) else self._eventos
        yield from eventos
