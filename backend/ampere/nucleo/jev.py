"""Cliente do Jev (TypeSafe AI): responde perguntas tipadas com probabilidades calibradas.

O Jev nunca gera texto (ver docs/adr/0001). Aqui só existem dois tipos de pergunta que o
sistema usa: sim ou não (`PerguntaSimNao`, devolve uma probabilidade) e escolha
(`PerguntaDeEscolha`, devolve a escolha, a confiança e a probabilidade de cada opção). Os dois
tipos são do projeto, não do SDK: o resto do sistema só conhece `ClienteJev`, e o SDK da
TypeSafe aparece apenas em `JevReal`, que traduz na ida e na volta (ver docs/adr/0008).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from ampere.regras import PerguntaDeEscolha, PerguntaSimNao

Pergunta = PerguntaSimNao | PerguntaDeEscolha
Perguntas = Mapping[str, Pergunta]
EstadoDoJev = str | dict | list


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

    def probabilidades(self) -> dict[str, float]:
        """Todas as probabilidades num único dicionário, para metadata de trace."""
        saida = {nome: r.probabilidade for nome, r in self.nouls.items()}
        for nome, r in self.choices.items():
            for opcao, p in r.probabilidades.items():
                saida[f"{nome}.{opcao}"] = p
        return saida


class ClienteJev(Protocol):
    def perguntar(self, estado: EstadoDoJev, perguntas: Perguntas) -> RespostasJev: ...


class JevReal:
    """Embrulha o SDK oficial da TypeSafe numa única chamada `system_one`."""

    def __init__(self, api_key: str | None, modelo: str = "jev-latest") -> None:
        if not api_key:
            raise ValueError("TYPESAFE_API_KEY ausente. Use MODELOS_FALSOS=true para rodar sem Jev")
        from typesafe_sdk import TypeSafeClient

        self._cliente = TypeSafeClient(api_key=api_key, model=modelo)

    def perguntar(self, estado: EstadoDoJev, perguntas: Perguntas) -> RespostasJev:
        resposta = self._cliente.system_one(
            state=estado, questions=self.traduzir_perguntas(perguntas)
        )
        return self.traduzir_resposta(resposta)

    @staticmethod
    def traduzir_perguntas(perguntas: Perguntas) -> dict[str, Any]:
        """Sim ou não vira `Noul`; escolha vira `Choice`."""
        from typesafe_sdk import Choice, Noul

        traduzidas: dict[str, Any] = {}
        for nome, pergunta in perguntas.items():
            if isinstance(pergunta, PerguntaSimNao):
                traduzidas[nome] = Noul(
                    instructions=pergunta.pergunta,
                    criteria={"true": pergunta.sim_quando, "false": pergunta.nao_quando},
                )
            else:
                traduzidas[nome] = Choice(
                    instructions=pergunta.pergunta, criteria=dict(pergunta.opcoes)
                )
        return traduzidas

    @staticmethod
    def traduzir_resposta(resposta: Any) -> RespostasJev:
        """De um `SystemOneResponse` do SDK para `RespostasJev`."""
        return RespostasJev(
            nouls={nome: RespostaNoul(r.noul) for nome, r in resposta.nouls.items()},
            choices={
                nome: RespostaChoice(r.choice, r.confidence, dict(r.probabilities))
                for nome, r in resposta.choices.items()
            },
        )
