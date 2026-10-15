"""Abrir Ticket: o trabalhador resume a Conversa em (resumo, categoria, prioridade) e o
Ticket fica gravado para um Atendente continuar o atendimento."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from psycopg.rows import class_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from ampere.nucleo.mensagens import formatar_conversa
from ampere.prompts import carregar_prompt

Categoria = Literal[
    "troca", "devolucao", "frete", "garantia", "pagamento", "cadastro", "reembolso", "outro"
]
Prioridade = Literal["baixa", "media", "alta"]

RESPOSTA_AO_ABRIR_TICKET = (
    "Entendi. Abri um Ticket para um Atendente humano continuar o seu atendimento. "
    "Você receberá o retorno em breve."
)


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
    def obter(self, ticket_id: str) -> Ticket | None: ...


class StoreDeTicketsEmMemoria:
    def __init__(self) -> None:
        self._tickets: list[Ticket] = []

    def criar(self, conversa_id: str, cliente_id: str, resumo: ResumoDoTicket) -> Ticket:
        ticket = Ticket(str(uuid4()), conversa_id, cliente_id, **resumo.model_dump())
        self._tickets.append(ticket)
        return ticket

    def listar(self) -> list[Ticket]:
        return list(reversed(self._tickets))

    def obter(self, ticket_id: str) -> Ticket | None:
        return next((t for t in self._tickets if t.id == ticket_id), None)


class StoreDeTicketsPostgres:
    """Tabela `tickets` (ver nucleo/migracoes)."""

    COLUNAS = "id::text, conversa_id::text, cliente_id, resumo, categoria, prioridade, criado_em"

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def criar(self, conversa_id: str, cliente_id: str, resumo: ResumoDoTicket) -> Ticket:
        return self._consultar(
            "INSERT INTO tickets (conversa_id, cliente_id, resumo, categoria, prioridade) "
            f"VALUES (%s, %s, %s, %s, %s) RETURNING {self.COLUNAS}",
            (conversa_id, cliente_id, resumo.resumo, resumo.categoria, resumo.prioridade),
        )[0]

    def listar(self) -> list[Ticket]:
        return self._consultar(f"SELECT {self.COLUNAS} FROM tickets ORDER BY criado_em DESC")

    def obter(self, ticket_id: str) -> Ticket | None:
        tickets = self._consultar(f"SELECT {self.COLUNAS} FROM tickets WHERE id = %s", (ticket_id,))
        return tickets[0] if tickets else None

    def _consultar(self, sql: str, parametros: tuple = ()) -> list[Ticket]:
        with self._pool.connection() as conn, conn.cursor(row_factory=class_row(Ticket)) as cur:
            return cur.execute(sql, parametros).fetchall()


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
        ],
        config={"metadata": prompt.metadata()},
    )
    return tickets.criar(conversa_id, cliente_id, resumo)
