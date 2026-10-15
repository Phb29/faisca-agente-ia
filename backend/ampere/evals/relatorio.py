"""O que os três evals têm em comum para virar uma Execução (ver docs/adr/0009): o relatório
(contexto, números de destaque e casos), o caso sorteado da amostra ao vivo e contas pequenas.

Todo caso, de qualquer eval, traz `id`, `texto` (a pergunta ou a mensagem), `grupo`,
`duracao_s` e `erro`, além dos campos do próprio eval: é com esses cinco que a faixa ao vivo
desenha os cartões sem saber de qual eval eles vêm. Os passos de um caso são um gerador que
solta o nome de cada fase quando ela começa e devolve o resultado no fim.
"""

from collections.abc import Generator, Sequence
from dataclasses import dataclass
from typing import Any

from ampere.nucleo.config import Config
from ampere.prompts import carregar_prompt

PassosDoCaso = Generator[str, None, dict]


@dataclass(frozen=True)
class Relatorio:
    contexto: dict
    resumo: dict
    casos: list[dict]


@dataclass(frozen=True)
class Sorteado:
    """Um caso da amostra: o que a faixa mostra antes de ele rodar e o item do golden."""

    id: str
    texto: str
    grupo: str
    item: Any

    def cartao(self) -> dict:
        return {"id": self.id, "texto": self.texto, "grupo": self.grupo}


def contexto_base(config: Config, *, prompts: Sequence[str], n: int) -> dict:
    """Com que modelos, em que modo e com que versão dos prompts a rodada aconteceu."""
    return {
        "modelos_falsos": config.modelos_falsos,
        "gerador": config.modelo_gerador,
        "juiz": config.modelo_juiz,
        "trabalhador": config.modelo_trabalhador,
        "prompts": {nome: carregar_prompt(nome).versao for nome in prompts},
        "n": n,
    }


def caso_com_erro(sorteado: Sorteado, erro: str, duracao_s: float) -> dict:
    return {**sorteado.cartao(), "duracao_s": round(duracao_s, 2), "erro": erro}


def consumir[T](passos: Generator[str, None, T]) -> T:
    """Roda os passos até o fim, sem olhar as fases, e devolve o resultado."""
    while True:
        try:
            next(passos)
        except StopIteration as fim:
            return fim.value


def media(valores: Sequence[float]) -> float | None:
    return sum(valores) / len(valores) if valores else None


def sem_erro(casos: Sequence[dict]) -> list[dict]:
    return [caso for caso in casos if not caso.get("erro")]
