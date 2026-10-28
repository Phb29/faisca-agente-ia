"""Cliente do Jev (TypeSafe AI): responde perguntas tipadas com probabilidades calibradas.

O Jev nunca gera texto (ver docs/adr/0001). Aqui só existem dois tipos de pergunta que o
sistema usa: sim ou não (`PerguntaSimNao`, devolve uma probabilidade) e escolha
(`PerguntaDeEscolha`, devolve a escolha, a confiança e a probabilidade de cada opção). Os dois
tipos são do projeto, não do SDK: o resto do sistema só conhece `ClienteJev`, e o SDK da
TypeSafe aparece apenas em `JevReal`, que traduz na ida e na volta (ver docs/adr/0008).
Sem chave da TypeSafe, `JevPorLLM` faz o mesmo papel com um modelo de chat comum.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from langchain_core.language_models import BaseChatModel

from ampere.prompts import carregar_prompt
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


class JevPorLLM:
    """Faz o papel do Jev com um modelo de chat comum (Groq ou OpenAI), que lê as mesmas
    perguntas e devolve as probabilidades em JSON. É mais lento que o Jev e a calibração é
    a que o modelo conseguir, mas não exige chave da TypeSafe."""

    TENTATIVAS = 2

    def __init__(self, modelo: BaseChatModel) -> None:
        self._modelo = modelo

    def perguntar(self, estado: EstadoDoJev, perguntas: Perguntas) -> RespostasJev:
        prompt = carregar_prompt("jev_por_llm").renderizar(
            perguntas=json.dumps(self.descrever_perguntas(perguntas), ensure_ascii=False, indent=2),
            estado=estado
            if isinstance(estado, str)
            else json.dumps(estado, ensure_ascii=False, default=str),
        )
        erro: Exception | None = None
        for _ in range(self.TENTATIVAS):
            texto = self._modelo.invoke(prompt).content
            try:
                return self.interpretar(str(texto), perguntas)
            except (ValueError, TypeError) as e:
                erro = e
        raise ValueError(f"O modelo não devolveu as respostas do Jev em JSON: {erro}")

    @staticmethod
    def descrever_perguntas(perguntas: Perguntas) -> dict[str, Any]:
        descritas: dict[str, Any] = {}
        for nome, pergunta in perguntas.items():
            if isinstance(pergunta, PerguntaSimNao):
                descritas[nome] = {
                    "tipo": "sim_nao",
                    "pergunta": pergunta.pergunta,
                    "sim quando": pergunta.sim_quando,
                    "não quando": pergunta.nao_quando,
                }
            else:
                descritas[nome] = {
                    "tipo": "escolha",
                    "pergunta": pergunta.pergunta,
                    "opcoes": dict(pergunta.opcoes),
                }
        return descritas

    @staticmethod
    def interpretar(texto: str, perguntas: Perguntas) -> RespostasJev:
        """Do JSON do modelo para `RespostasJev`. Pergunta faltando é erro; probabilidades de
        escolha são normalizadas para somar 1."""
        inicio, fim = texto.find("{"), texto.rfind("}")
        if inicio < 0 or fim < inicio:
            raise ValueError("resposta sem objeto JSON")
        dados = json.loads(texto[inicio : fim + 1])
        respostas = RespostasJev()
        for nome, pergunta in perguntas.items():
            if nome not in dados:
                raise ValueError(f"faltou a pergunta {nome}")
            if isinstance(pergunta, PerguntaSimNao):
                respostas.nouls[nome] = RespostaNoul(min(max(float(dados[nome]), 0.0), 1.0))
                continue
            brutas = {o: max(float(dados[nome].get(o, 0.0)), 0.0) for o in pergunta.opcoes}
            total = sum(brutas.values())
            if total == 0:
                raise ValueError(f"nenhuma opção com probabilidade em {nome}")
            probabilidades = {o: p / total for o, p in brutas.items()}
            escolha = max(probabilidades, key=probabilidades.__getitem__)
            respostas.choices[nome] = RespostaChoice(
                escolha, probabilidades[escolha], probabilidades
            )
        return respostas
