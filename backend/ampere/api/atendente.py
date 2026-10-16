"""Rotas do Atendente, protegidas pela sessão de login: Aprovações Pendentes (aprovar e
rejeitar viram jobs de retomada na fila), Tickets e Memória Procedural de cada Cliente."""

from typing import Annotated, Protocol

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ampere.acoes.aprovacoes import Aprovacao, decidir_aprovacao, listar_pendentes, obter_aprovacao
from ampere.acoes.ticket import StoreDeTicketsPostgres, Ticket
from ampere.api.dependencias import Conexao, Pool, exigir_sessao, uuid_ou_404
from ampere.conversas.conversas import Mensagem, listar_mensagens
from ampere.fila.fila import enfileirar_retomada
from ampere.memoria.procedural import MAXIMO_DE_PREFERENCIAS, TAMANHO_DA_PREFERENCIA


class MemoriaProcedural(Protocol):
    """O que a API precisa da Memória Procedural: as instruções do Atendente e as preferências
    pedidas pelo Cliente. A implementação real está em `ampere.memoria.procedural`, sobre o
    Store do LangGraph; os testes usam um dicionário."""

    def ler(self, cliente_id: str) -> str: ...
    def escrever(self, cliente_id: str, texto: str) -> None: ...
    def ler_preferencias(self, cliente_id: str) -> list[str]: ...
    def escrever_preferencias(self, cliente_id: str, itens: list[str]) -> None: ...


class Rejeicao(BaseModel):
    motivo: str | None = Field(default=None, max_length=1000)


Preferencia = Annotated[str, Field(max_length=TAMANHO_DA_PREFERENCIA)]


class EdicaoProcedural(BaseModel):
    """Sem `preferencias`, a lista fica como está; com ela, a lista é substituída, e é assim
    que o Atendente apaga uma preferência ou todas."""

    texto: str = Field(max_length=4000)
    preferencias: list[Preferencia] | None = Field(default=None, max_length=MAXIMO_DE_PREFERENCIAS)


class MemoriaProceduralDoCliente(BaseModel):
    texto: str
    preferencias: list[str]


class ConversaDoTicket(BaseModel):
    ticket: Ticket
    mensagens: list[Mensagem]


router = APIRouter(prefix="/atendente", dependencies=[Depends(exigir_sessao)])


def _memoria(request: Request) -> MemoriaProcedural:
    memoria = request.app.state.memoria_procedural
    if memoria is None:
        raise HTTPException(status_code=503, detail="Memória Procedural não configurada")
    return memoria


def _decidir(conn: psycopg.Connection, aprovacao_id: str, aprovada: bool, motivo: str | None):
    """Decisão e job de retomada numa transação só: ou os dois existem, ou nenhum."""
    aprovacao_id = uuid_ou_404(aprovacao_id)
    with conn.transaction():
        if obter_aprovacao(conn, aprovacao_id) is None:
            raise HTTPException(status_code=404, detail="Aprovação não encontrada")
        decidida = decidir_aprovacao(conn, aprovacao_id, aprovada, motivo)
        if decidida is None:
            raise HTTPException(status_code=409, detail="Aprovação já decidida")
        job_id = enfileirar_retomada(
            conn, decidida.conversa_id, aprovacao_id, aprovada, motivo, decidida.cliente_id
        )
    return {"job_id": job_id}


@router.get("/aprovacoes")
def aprovacoes(conn: Conexao) -> list[Aprovacao]:
    return listar_pendentes(conn)


@router.post("/aprovacoes/{aprovacao_id}/aprovar")
def aprovar(conn: Conexao, aprovacao_id: str) -> dict:
    return _decidir(conn, aprovacao_id, True, None)


@router.post("/aprovacoes/{aprovacao_id}/rejeitar")
def rejeitar(conn: Conexao, aprovacao_id: str, corpo: Rejeicao | None = None) -> dict:
    motivo = (corpo.motivo or "").strip() if corpo else ""
    return _decidir(conn, aprovacao_id, False, motivo or None)


@router.get("/tickets")
def tickets(pool: Pool) -> list[Ticket]:
    return StoreDeTicketsPostgres(pool).listar()


@router.get("/tickets/{ticket_id}/conversa")
def conversa_do_ticket(pool: Pool, conn: Conexao, ticket_id: str) -> ConversaDoTicket:
    ticket = StoreDeTicketsPostgres(pool).obter(uuid_ou_404(ticket_id))
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    return ConversaDoTicket(ticket=ticket, mensagens=listar_mensagens(conn, ticket.conversa_id))


def _ler(memoria: MemoriaProcedural, cliente_id: str) -> MemoriaProceduralDoCliente:
    return MemoriaProceduralDoCliente(
        texto=memoria.ler(cliente_id), preferencias=memoria.ler_preferencias(cliente_id)
    )


@router.get("/clientes/{cliente_id}/memoria-procedural")
def ler_memoria(request: Request, cliente_id: str) -> MemoriaProceduralDoCliente:
    return _ler(_memoria(request), cliente_id)


@router.put("/clientes/{cliente_id}/memoria-procedural")
def escrever_memoria(
    request: Request, cliente_id: str, corpo: EdicaoProcedural
) -> MemoriaProceduralDoCliente:
    memoria = _memoria(request)
    memoria.escrever(cliente_id, corpo.texto)
    if corpo.preferencias is not None:
        memoria.escrever_preferencias(cliente_id, corpo.preferencias)
    return _ler(memoria, cliente_id)
