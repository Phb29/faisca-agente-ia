"""As três memórias de longo prazo de um Cliente, como o grafo as recebe no início do turno.

A Procedural chega em duas partes: `procedural`, as instruções do Atendente, e `preferencias`,
o que o próprio Cliente pediu sobre a forma de falar.
"""

from typing import TypedDict


class Episodio(TypedDict):
    resumo: str
    desfecho: str
    acoes: list[str]
    data: str


class Memorias(TypedDict):
    semantica: list[str]
    episodica: list[Episodio]
    procedural: str
    preferencias: list[str]


def memorias_vazias() -> Memorias:
    return {"semantica": [], "episodica": [], "procedural": "", "preferencias": []}
