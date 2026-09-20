"""Estado da Conversa que atravessa os oito nós do grafo (Memória de Curto Prazo)."""

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

Intencao = Literal["duvida", "transacao", "quer_humano"]
Desfecho = Literal["Resolvida", "Escalada", "Aprovação Pendente"]
Bloqueio = Literal["manipulacao", "fora_de_escopo"]


class Memorias(TypedDict):
    semantica: list[str]
    episodica: list[dict]
    procedural: str


class EstadoDaConversa(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    cliente_id: str
    conversa_id: str
    memorias: Memorias
    mensagem_sensivel: bool
    bloqueio: Bloqueio | None
    intencao: Intencao | None
    contexto: list[dict]
    resposta_candidata: str | None
    critica: str | None
    tentativas: int
    acoes_tomadas: list[str]
    desfecho: Desfecho | None
    resumo: str | None


def memorias_vazias() -> Memorias:
    return {"semantica": [], "episodica": [], "procedural": ""}
