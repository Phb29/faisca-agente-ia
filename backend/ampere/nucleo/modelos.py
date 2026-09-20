"""Fábrica de modelos: três papéis nomeados (ver docs/adr/0002) mais o Jev.

Gerador escreve para o Cliente e decide qual Ação chamar. Juiz só roda nos evals e é
deliberadamente diferente do gerador. Trabalhador faz as tarefas de bastidor do tipo
"leia texto e devolva JSON". Com `modelos_falsos=True`, tudo vira falso e nenhum token é gasto.
"""

from langchain_core.language_models import BaseChatModel

from ampere.nucleo.config import Config
from ampere.nucleo.falsos import JevFalso, ModeloFalso
from ampere.nucleo.jev import ClienteJev, JevReal

# USD por milhão de tokens (entrada, saída), para a tabela de custo do README.
CUSTO_POR_PAPEL: dict[str, dict[str, float | str]] = {
    "gerador": {"modelo": "gpt-5.6-terra", "entrada": 2.50, "saida": 10.00},
    "juiz": {"modelo": "gpt-5.6-sol", "entrada": 15.00, "saida": 60.00},
    "trabalhador": {"modelo": "openai/gpt-oss-120b (Groq)", "entrada": 0.15, "saida": 0.60},
}


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
            self._gerador = self._openai(self.config.modelo_gerador)
        return self._gerador

    def juiz(self) -> BaseChatModel:
        if self._juiz is None:
            self._juiz = self._openai(self.config.modelo_juiz)
        return self._juiz

    def trabalhador(self) -> BaseChatModel:
        if self._trabalhador is None:
            if self.config.modelos_falsos:
                self._trabalhador = ModeloFalso()
            else:
                from langchain_groq import ChatGroq

                self._trabalhador = ChatGroq(
                    model=self.config.modelo_trabalhador,
                    api_key=self.config.groq_api_key,
                    temperature=0,
                )
        return self._trabalhador

    def jev(self) -> ClienteJev:
        if self._jev is None:
            if self.config.modelos_falsos:
                self._jev = JevFalso()
            else:
                self._jev = JevReal(self.config.typesafe_api_key)
        return self._jev

    def _openai(self, modelo: str) -> BaseChatModel:
        if self.config.modelos_falsos:
            return ModeloFalso()
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=modelo, api_key=self.config.openai_api_key, streaming=True)
