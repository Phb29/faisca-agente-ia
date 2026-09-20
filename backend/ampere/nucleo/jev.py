"""Cliente do Jev (TypeSafe AI): responde perguntas tipadas com probabilidades calibradas.

O Jev nunca gera texto (ver docs/adr/0001). Aqui só existem dois tipos de pergunta que o
sistema usa: Noul (sim/não, devolve uma probabilidade) e Choice (uma opção entre várias,
devolve a escolha, a confiança e a probabilidade de cada opção).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from typesafe_sdk import Choice, Noul, SystemOneResponse, TypeSafeClient

Perguntas = Mapping[str, Noul | Choice]
Estado = str | dict | list


@dataclass(frozen=True)
class RespostaNoul:
    probabilidade: float


@dataclass(frozen=True)
class RespostaChoice:
    escolha: str
    confianca: float
    probabilidades: dict[str, float]


@dataclass
class RespostasJev:
    nouls: dict[str, RespostaNoul] = field(default_factory=dict)
    choices: dict[str, RespostaChoice] = field(default_factory=dict)

    @classmethod
    def do_sdk(cls, resposta: SystemOneResponse) -> "RespostasJev":
        return cls(
            nouls={nome: RespostaNoul(r.noul) for nome, r in resposta.nouls.items()},
            choices={
                nome: RespostaChoice(r.choice, r.confidence, dict(r.probabilities))
                for nome, r in resposta.choices.items()
            },
        )

    def probabilidades(self) -> dict[str, float]:
        """Todas as probabilidades num único dicionário, para metadata de trace."""
        saida = {nome: r.probabilidade for nome, r in self.nouls.items()}
        for nome, r in self.choices.items():
            for opcao, p in r.probabilidades.items():
                saida[f"{nome}.{opcao}"] = p
        return saida


class ClienteJev(Protocol):
    def perguntar(self, estado: Estado, perguntas: Perguntas) -> RespostasJev: ...


class JevReal:
    """Embrulha o SDK oficial da TypeSafe numa única chamada `system_one`."""

    def __init__(self, api_key: str | None, modelo: str = "jev-latest") -> None:
        if not api_key:
            raise ValueError("TYPESAFE_API_KEY ausente. Use MODELOS_FALSOS=true para rodar sem Jev")
        self._cliente = TypeSafeClient(api_key=api_key, model=modelo)

    def perguntar(self, estado: Estado, perguntas: Perguntas) -> RespostasJev:
        resposta = self._cliente.system_one(state=estado, questions=dict(perguntas))
        return RespostasJev.do_sdk(resposta)
