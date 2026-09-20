"""Modelos falsos para testes e para rodar o sistema inteiro sem gastar um token.

`ModeloFalso` é um chat model do LangChain que devolve respostas roteirizadas.
`JevFalso` devolve probabilidades fixas por nome de pergunta. Os dois são injetados
pela mesma fábrica que injeta os modelos reais (`ampere.nucleo.modelos`).
"""

import json
from collections.abc import Iterator, Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, Field
from typesafe_sdk import Choice, Noul

from ampere.nucleo.jev import Estado, Perguntas, RespostaChoice, RespostaNoul, RespostasJev

Resposta = AIMessage | str | BaseModel


class ModeloFalso(BaseChatModel):
    """Devolve as respostas na ordem dada; quando acabam, repete a última."""

    respostas: list[Any] = Field(default_factory=list)
    chamadas: list[list[BaseMessage]] = Field(default_factory=list)
    _posicao: int = 0

    def __init__(self, respostas: Sequence[Resposta] | None = None, **kwargs: Any) -> None:
        super().__init__(respostas=list(respostas or ["ok"]), **kwargs)

    @property
    def _llm_type(self) -> str:
        return "modelo-falso"

    def _proxima(self, tipo: type | None = None) -> Any:
        candidatos = self.respostas[self._posicao :] or self.respostas[-1:]
        for deslocamento, resposta in enumerate(candidatos):
            if tipo is None or isinstance(resposta, tipo):
                self._posicao = min(self._posicao + deslocamento + 1, len(self.respostas))
                return resposta
        raise AssertionError(f"ModeloFalso sem resposta do tipo {tipo}")

    def _proxima_mensagem(self) -> AIMessage:
        resposta = self._proxima(AIMessage | str)
        return resposta if isinstance(resposta, AIMessage) else AIMessage(content=resposta)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.chamadas.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=self._proxima_mensagem())])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        self.chamadas.append(list(messages))
        mensagem = self._proxima_mensagem()
        if mensagem.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=mensagem.content,
                    tool_calls=mensagem.tool_calls,
                    tool_call_chunks=[
                        {
                            "name": tc["name"],
                            "args": json.dumps(tc["args"]),
                            "id": tc["id"],
                            "index": i,
                        }
                        for i, tc in enumerate(mensagem.tool_calls)
                    ],
                )
            )
            return
        palavras = str(mensagem.content).split(" ")
        for i, palavra in enumerate(palavras):
            pedaco = palavra if i == len(palavras) - 1 else palavra + " "
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=pedaco))
            if run_manager:
                run_manager.on_llm_new_token(pedaco, chunk=chunk)
            yield chunk

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Runnable:
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:
        def responder(entrada: Any) -> BaseModel:
            self.chamadas.append(list(entrada) if isinstance(entrada, list) else [entrada])
            return self._proxima(schema)

        return RunnableLambda(responder)


class JevFalso:
    """Devolve probabilidade fixa por nome de pergunta (0.0 por padrão) e escolha fixa."""

    def __init__(
        self,
        nouls: dict[str, float] | None = None,
        choices: dict[str, str] | None = None,
    ) -> None:
        self.nouls = dict(nouls or {})
        self.choices = dict(choices or {})
        self.chamadas: list[tuple[Estado, Perguntas]] = []

    def perguntar(self, estado: Estado, perguntas: Perguntas) -> RespostasJev:
        self.chamadas.append((estado, perguntas))
        respostas = RespostasJev()
        for nome, pergunta in perguntas.items():
            if isinstance(pergunta, Noul):
                respostas.nouls[nome] = RespostaNoul(self.nouls.get(nome, 0.0))
            elif isinstance(pergunta, Choice):
                opcoes = list(pergunta.criteria)
                escolha = self.choices.get(nome, opcoes[0])
                probabilidades = {o: (1.0 if o == escolha else 0.0) for o in opcoes}
                respostas.choices[nome] = RespostaChoice(escolha, 1.0, probabilidades)
        return respostas


def embed_falso(textos: list[str]) -> list[list[float]]:
    """Vetor de 384 dimensões por bag-of-words hasheado: determinístico e sem modelo."""
    import hashlib
    import math
    import re

    vetores = []
    for texto in textos:
        vetor = [0.0] * 384
        for palavra in re.findall(r"\w+", texto.lower()):
            indice = int(hashlib.md5(palavra.encode()).hexdigest(), 16) % 384
            vetor[indice] += 1.0
        norma = math.sqrt(sum(v * v for v in vetor)) or 1.0
        vetores.append([v / norma for v in vetor])
    return vetores


def cosseno(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))
