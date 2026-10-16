"""Fábrica de modelos: três papéis nomeados (ver docs/adr/0002) mais o Jev.

Gerador escreve para o Cliente e decide qual Ação chamar. Juiz só roda nos evals e é
deliberadamente diferente do gerador. Trabalhador faz as tarefas de bastidor do tipo
"leia texto e devolva JSON". O provedor e o modelo de cada papel vêm da Config, e `_chat` é o
único lugar que conhece o pacote de cada provedor (ver docs/adr/0008). Com
`modelos_falsos=True`, entram os dublês do modo demonstração (`demonstracao.py`): nenhum token
é gasto e nada depende do Jev estar no ar.
"""

from typing import Any

from langchain_core.language_models import BaseChatModel

from ampere.nucleo.config import Config, Provedor
from ampere.nucleo.demonstracao import (
    GeradorDeDemonstracao,
    JevDeDemonstracao,
    TrabalhadorDeDemonstracao,
)
from ampere.nucleo.falsos import ModeloFalso
from ampere.nucleo.jev import ClienteJev, JevReal


class FabricaDeModelos:
    def __init__(
        self,
        config: Config,
        *,
        gerador: BaseChatModel | None = None,
        juiz: BaseChatModel | None = None,
        trabalhador: BaseChatModel | None = None,
        jev: ClienteJev | None = None,
    ) -> None:
        self.config = config
        self._gerador = gerador
        self._juiz = juiz
        self._trabalhador = trabalhador
        self._jev = jev

    def gerador(self) -> BaseChatModel:
        if self._gerador is None:
            falso = GeradorDeDemonstracao() if self.config.modelos_falsos else None
            provedor = self.config.provedor_gerador
            # O agente usa tools, e a API de chat completions da OpenAI recusa tools com
            # raciocínio ligado nos modelos de raciocínio (gpt-5.6, gpt-6): lá o gerador
            # roda sem ele.
            sem_raciocinio = {"reasoning_effort": "none"} if provedor == "openai" else {}
            self._gerador = falso or self._chat(
                provedor, self.config.modelo_gerador, streaming=True, **sem_raciocinio
            )
        return self._gerador

    def juiz(self) -> BaseChatModel:
        if self._juiz is None:
            falso = ModeloFalso() if self.config.modelos_falsos else None
            self._juiz = falso or self._chat(
                self.config.provedor_juiz, self.config.modelo_juiz, streaming=True
            )
        return self._juiz

    def trabalhador(self) -> BaseChatModel:
        if self._trabalhador is None:
            if self.config.modelos_falsos:
                self._trabalhador = TrabalhadorDeDemonstracao()
            else:
                self._trabalhador = self._chat(
                    self.config.provedor_trabalhador,
                    self.config.modelo_trabalhador,
                    temperature=0,
                )
        return self._trabalhador

    def jev(self) -> ClienteJev:
        if self._jev is None:
            if self.config.modelos_falsos:
                self._jev = JevDeDemonstracao()
            else:
                self._jev = JevReal(self.config.typesafe_api_key)
        return self._jev

    def _chat(self, provedor: Provedor, modelo: str, **opcoes: Any) -> BaseChatModel:
        """Um provedor novo é mais um `if` aqui, a chave dele na Config e o nome em `Provedor`."""
        if provedor == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(model=modelo, api_key=self.config.openai_api_key, **opcoes)
        if provedor == "groq":
            from langchain_groq import ChatGroq

            return ChatGroq(model=modelo, api_key=self.config.groq_api_key, **opcoes)
        raise ValueError(f"Provedor desconhecido: {provedor}")
