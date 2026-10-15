"""As três memórias de longo prazo de um Cliente, como o grafo as recebe no início do turno."""

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


def memorias_vazias() -> Memorias:
    return {"semantica": [], "episodica": [], "procedural": ""}
