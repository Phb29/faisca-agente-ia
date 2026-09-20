"""Rotas do Atendente, protegidas por `X-Atendente-Token`: Aprovações Pendentes (aprovar e
rejeitar viram jobs de retomada), Tickets e Memória Procedural de cada Cliente."""

from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ampere.api.seguranca import Conexao, exigir_atendente, uuid_ou_404
from ampere.fila.fila import (
    decidir_aprovacao,
    enfileirar_retomada,
    listar_aprovacoes_pendentes,
    listar_mensagens,
    listar_tickets,
    obter_aprovacao,
    obter_ticket,
)


class MemoriaProcedural(Protocol):
    """O que a API precisa da Memória Procedural. A implementação real vive em
    `ampere.memoria`, sobre o Store do LangGraph; os testes usam um dicionário."""

    def ler(self, cliente_id: str) -> str: ...
    def escrever(self, cliente_id: str, texto: str) -> None: ...


class Rejeicao(BaseModel):
    motivo: str | None = None


class TextoProcedural(BaseModel):
    texto: str


router = APIRouter(prefix="/atendente", dependencies=[Depends(exigir_atendente)])


def _memoria(request: Request) -> MemoriaProcedural:
    memoria = getattr(request.app.state, "memoria_procedural", None)
    if memoria is None:
        raise HTTPException(status_code=503, detail="Memória Procedural não configurada")
    return memoria


def _decidir(conn, aprovacao_id: str, aprovada: bool, motivo: str | None) -> dict:
    aprovacao_id = uuid_ou_404(aprovacao_id)
    aprovacao = obter_aprovacao(conn, aprovacao_id)
    if aprovacao is None:
        raise HTTPException(status_code=404, detail="Aprovação não encontrada")
    decidida = decidir_aprovacao(conn, aprovacao_id, aprovada, motivo)
    if decidida is None:
        raise HTTPException(status_code=409, detail="Aprovação já decidida")
    job_id = enfileirar_retomada(
        conn, decidida["conversa_id"], aprovacao_id, aprovada, motivo, decidida["cliente_id"]
    )
    return {"job_id": job_id}


@router.get("/aprovacoes")
def aprovacoes(conn: Conexao) -> list[dict]:
    return listar_aprovacoes_pendentes(conn)


@router.post("/aprovacoes/{aprovacao_id}/aprovar")
def aprovar(conn: Conexao, aprovacao_id: str) -> dict:
    return _decidir(conn, aprovacao_id, True, None)


@router.post("/aprovacoes/{aprovacao_id}/rejeitar")
def rejeitar(conn: Conexao, aprovacao_id: str, corpo: Rejeicao | None = None) -> dict:
    return _decidir(conn, aprovacao_id, False, corpo.motivo if corpo else None)


@router.get("/tickets")
def tickets(conn: Conexao) -> list[dict]:
    return listar_tickets(conn)


@router.get("/tickets/{ticket_id}/conversa")
def conversa_do_ticket(conn: Conexao, ticket_id: str) -> dict:
    ticket = obter_ticket(conn, uuid_ou_404(ticket_id))
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    return {"ticket": ticket, "mensagens": listar_mensagens(conn, ticket["conversa_id"])}


@router.get("/clientes/{cliente_id}/memoria-procedural")
def ler_memoria(request: Request, cliente_id: str) -> dict:
    return {"texto": _memoria(request).ler(cliente_id)}


@router.put("/clientes/{cliente_id}/memoria-procedural")
def escrever_memoria(request: Request, cliente_id: str, corpo: TextoProcedural) -> dict:
    _memoria(request).escrever(cliente_id, corpo.texto)
    return {"texto": corpo.texto}
