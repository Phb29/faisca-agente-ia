"""Abrir Ticket: o trabalhador resume a Conversa em (resumo, categoria, prioridade)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from ampere.grafo.prompts import carregar_prompt

Categoria = Literal[
    "troca", "devolucao", "frete", "garantia", "pagamento", "cadastro", "reembolso", "outro"
]
Prioridade = Literal["baixa", "media", "alta"]


class ResumoDoTicket(BaseModel):
    resumo: str
    categoria: Categoria
    prioridade: Prioridade


@dataclass(frozen=True)
class Ticket:
    id: str
    conversa_id: str
    cliente_id: str
    resumo: str
    categoria: str
    prioridade: str
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))


class StoreDeTickets(Protocol):
    def criar(self, conversa_id: str, cliente_id: str, resumo: ResumoDoTicket) -> Ticket: ...
    def listar(self) -> list[Ticket]: ...


class StoreDeTicketsEmMemoria:
    def __init__(self) -> None:
        self._tickets: list[Ticket] = []

    def criar(self, conversa_id: str, cliente_id: str, resumo: ResumoDoTicket) -> Ticket:
        ticket = Ticket(
            id=str(uuid4()),
            conversa_id=conversa_id,
            cliente_id=cliente_id,
            resumo=resumo.resumo,
            categoria=resumo.categoria,
            prioridade=resumo.prioridade,
        )
        self._tickets.append(ticket)
        return ticket

    def listar(self) -> list[Ticket]:
        return list(self._tickets)


class StoreDeTicketsPostgres:
    """Grava na tabela `tickets` (ver fila/migracoes)."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def criar(self, conversa_id: str, cliente_id: str, resumo: ResumoDoTicket) -> Ticket:
        linha = self._conn.execute(
            "INSERT INTO tickets (conversa_id, cliente_id, resumo, categoria, prioridade) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id, criado_em",
            (conversa_id, cliente_id, resumo.resumo, resumo.categoria, resumo.prioridade),
        ).fetchone()
        self._conn.commit()
        return Ticket(
            id=str(linha["id"]),
            conversa_id=conversa_id,
            cliente_id=cliente_id,
            resumo=resumo.resumo,
            categoria=resumo.categoria,
            prioridade=resumo.prioridade,
            criado_em=linha["criado_em"],
        )

    def listar(self) -> list[Ticket]:
        linhas = self._conn.execute("SELECT * FROM tickets ORDER BY criado_em DESC").fetchall()
        return [
            Ticket(
                id=str(r["id"]),
                conversa_id=str(r["conversa_id"]),
                cliente_id=r["cliente_id"],
                resumo=r["resumo"],
                categoria=r["categoria"],
                prioridade=r["prioridade"],
                criado_em=r["criado_em"],
            )
            for r in linhas
        ]


def formatar_conversa(messages: list[BaseMessage]) -> str:
    linhas = []
    for mensagem in messages:
        if isinstance(mensagem, HumanMessage):
            linhas.append(f"Cliente: {mensagem.content}")
        elif isinstance(mensagem, AIMessage) and mensagem.content:
            linhas.append(f"Assistente: {mensagem.content}")
    return "\n".join(linhas)


def abrir_ticket(
    trabalhador: BaseChatModel,
    tickets: StoreDeTickets,
    *,
    conversa_id: str,
    cliente_id: str,
    messages: list[BaseMessage],
) -> Ticket:
    prompt = carregar_prompt("resumir_ticket")
    resumo = trabalhador.with_structured_output(ResumoDoTicket).invoke(
        [
            SystemMessage(prompt.renderizar(conversa=formatar_conversa(messages))),
            HumanMessage("Resuma esta Conversa para o Ticket."),
        ]
    )
    return tickets.criar(conversa_id, cliente_id, resumo)
