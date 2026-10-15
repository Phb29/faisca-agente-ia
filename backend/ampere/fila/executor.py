"""Quem executa um job. O worker só conhece este Protocol; o executor de verdade, que roda o
grafo, vive em `ampere.grafo.executor`, e quem liga um ao outro é a raiz de composição
(`ampere/cli.py`). Assim a fila não sabe nada do grafo.

Os dados de cada evento seguem a convenção de `ampere.fila.eventos`.
"""

from collections.abc import Callable, Iterator
from typing import Protocol

from ampere.fila.eventos import Evento
from ampere.fila.fila import Job


class Executor(Protocol):
    def executar(self, job: Job) -> Iterator[Evento]: ...


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
