"""Rotas do Cliente: Conversas, mensagens (202 idempotente) e a lista de Clientes seed."""

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ampere.api.seguranca import ClienteId, Conexao, uuid_ou_404
from ampere.fila.fila import (
    criar_conversa,
    enfileirar_mensagem,
    listar_clientes,
    listar_conversas,
    listar_mensagens,
    obter_conversa,
)

router = APIRouter()


class NovaConversa(BaseModel):
    titulo: str | None = None


class NovaMensagem(BaseModel):
    message_id: str
    conteudo: str


def conversa_do_cliente(conn: psycopg.Connection, conversa_id: str, cliente_id: str) -> dict:
    """Devolve a Conversa se for deste Cliente; 404 caso contrário (não vazamos que existe)."""
    conversa = obter_conversa(conn, uuid_ou_404(conversa_id))
    if conversa is None or conversa["cliente_id"] != cliente_id:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    return conversa


@router.get("/clientes")
def clientes(conn: Conexao) -> list[dict]:
    return listar_clientes(conn)


@router.post("/conversas", status_code=201)
def criar(conn: Conexao, cliente_id: ClienteId, corpo: NovaConversa | None = None) -> dict:
    titulo = corpo.titulo if corpo else None
    return {"id": criar_conversa(conn, cliente_id, titulo)}


@router.get("/conversas")
def listar(conn: Conexao, cliente_id: ClienteId) -> list[dict]:
    return listar_conversas(conn, cliente_id)


@router.get("/conversas/{conversa_id}")
def detalhe(conn: Conexao, cliente_id: ClienteId, conversa_id: str) -> dict:
    return conversa_do_cliente(conn, conversa_id, cliente_id)


@router.post("/conversas/{conversa_id}/mensagens", status_code=202)
def enviar(conn: Conexao, cliente_id: ClienteId, conversa_id: str, corpo: NovaMensagem) -> dict:
    conversa = conversa_do_cliente(conn, conversa_id, cliente_id)
    enfileirada = enfileirar_mensagem(
        conn, conversa["id"], corpo.message_id, corpo.conteudo, cliente_id
    )
    return {"enfileirada": enfileirada}


@router.get("/conversas/{conversa_id}/mensagens")
def mensagens(conn: Conexao, cliente_id: ClienteId, conversa_id: str) -> list[dict]:
    conversa = conversa_do_cliente(conn, conversa_id, cliente_id)
    return listar_mensagens(conn, conversa["id"])
