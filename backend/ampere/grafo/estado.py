"""Estado da Conversa que atravessa os nós do grafo (a Memória de Curto Prazo).

`messages` e `resumo` duram a Conversa inteira; todo o resto é do turno e volta ao valor
inicial em `carregar_memoria`, no começo de cada mensagem do Cliente.
"""

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from ampere.acoes.reembolso import DecisaoGravada
from ampere.memoria.tipos import Memorias
from ampere.roteador.roteador import Intencao

Desfecho = Literal["Resolvida", "Escalada"]
EscaladaPor = Literal["pedido_do_cliente", "guardrail_saida"]


class EstadoDaConversa(TypedDict, total=False):
    # da Conversa
    messages: Annotated[list[AnyMessage], add_messages]
    cliente_id: str
    conversa_id: str
    resumo: str | None
    # do turno
    memorias: Memorias
    mensagem_sensivel: bool
    bloqueio: str | None
    intencao: Intencao | None
    contexto: list[dict]
    decisoes_do_gate: dict[str, DecisaoGravada]
    resposta_candidata: str | None
    critica: str | None
    motivo_da_reprovacao: str | None
    tentativas: int
    escalada_por: EscaladaPor | None
    acoes_tomadas: list[str]
    desfecho: Desfecho | None


def inicio_do_turno(memorias: Memorias) -> EstadoDaConversa:
    """Os campos do turno zerados, com as memórias recém-carregadas."""
    return {
        "memorias": memorias,
        "mensagem_sensivel": False,
        "bloqueio": None,
        "intencao": None,
        "contexto": [],
        "decisoes_do_gate": {},
        "resposta_candidata": None,
        "critica": None,
        "motivo_da_reprovacao": None,
        "tentativas": 0,
        "escalada_por": None,
        "acoes_tomadas": [],
        "desfecho": None,
    }
