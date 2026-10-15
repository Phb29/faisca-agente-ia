"""Self-querying: o trabalhador lê a pergunta do Cliente e devolve um FiltroDeBusca."""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ampere.prompts import carregar_prompt
from ampere.rag.filtro import FiltroDeBusca

log = logging.getLogger(__name__)


class SelfQuerying:
    def __init__(self, trabalhador: BaseChatModel) -> None:
        self.trabalhador = trabalhador
        self.prompt = carregar_prompt("self_querying")

    def gerar_filtro(self, pergunta: str) -> FiltroDeBusca:
        """O filtro é só um atalho da busca. Se o modelo falhar (às vezes ele recusa a
        pergunta e não chama a ferramenta), a busca segue sem filtro, na Base inteira."""
        sistema = self.prompt.renderizar(pergunta=pergunta)
        try:
            resposta = self.trabalhador.with_structured_output(FiltroDeBusca).invoke(
                [SystemMessage(content=sistema), HumanMessage(content=pergunta)],
                config={"metadata": self.prompt.metadata()},
            )
        except Exception:  # noqa: BLE001 - qualquer falha do modelo vira busca sem filtro
            log.warning("self-querying falhou; a busca segue sem filtro", exc_info=True)
            return FiltroDeBusca()
        if isinstance(resposta, FiltroDeBusca):
            return resposta
        return FiltroDeBusca.model_validate(resposta)
