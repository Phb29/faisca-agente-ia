"""Self-querying: o trabalhador lê a pergunta do Cliente e devolve um FiltroDeBusca."""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ampere.grafo.prompts import carregar_prompt
from ampere.rag.filtro import FiltroDeBusca


class SelfQuerying:
    def __init__(self, trabalhador: BaseChatModel) -> None:
        self.trabalhador = trabalhador
        self.prompt = carregar_prompt("self_querying")

    def gerar_filtro(self, pergunta: str) -> FiltroDeBusca:
        sistema = self.prompt.renderizar(pergunta=pergunta)
        resposta = self.trabalhador.with_structured_output(FiltroDeBusca).invoke(
            [SystemMessage(content=sistema), HumanMessage(content=pergunta)]
        )
        if isinstance(resposta, FiltroDeBusca):
            return resposta
        return FiltroDeBusca.model_validate(resposta)
