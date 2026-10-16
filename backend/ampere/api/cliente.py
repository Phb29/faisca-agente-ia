"""Rotas do Cliente, protegidas pela sessão de login: Clientes e Pedidos para o chat,
Conversas e mensagens (202 idempotente).

Toda mensagem é mascarada aqui, na borda, antes de qualquer gravação: cartão, CPF, CVV e
senha nunca chegam ao transcript, à fila, ao checkpoint nem ao trace.
"""

from datetime import date

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ampere.api.dependencias import ClienteId, Conexao, Pool, exigir_sessao, uuid_ou_404
from ampere.conversas.conversas import (
    Conversa,
    Mensagem,
    criar_conversa,
    listar_conversas,
    listar_mensagens,
    obter_conversa,
)
from ampere.fila.fila import enfileirar_mensagem
from ampere.guardrails.mascaramento import mascarar
from ampere.loja.pedidos import Cliente, StoreDePedidosPostgres, listar_clientes

router = APIRouter(dependencies=[Depends(exigir_sessao)])


class NovaConversa(BaseModel):
    titulo: str | None = None


class NovaMensagem(BaseModel):
    message_id: str = Field(min_length=1, max_length=100)
    conteudo: str = Field(min_length=1, max_length=4000)


class MensagemRecebida(BaseModel):
    enfileirada: bool
    conteudo: str


class PedidoDoCliente(BaseModel):
    id: str
    cliente_id: str
    produto: str
    linha: str
    valor: float
    status: str
    data: date


def conversa_do_cliente(conn: psycopg.Connection, conversa_id: str, cliente_id: str) -> Conversa:
    """A Conversa, se for deste Cliente; 404 caso contrário (sem revelar que ela existe)."""
    conversa = obter_conversa(conn, uuid_ou_404(conversa_id))
    if conversa is None or conversa.cliente_id != cliente_id:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    return conversa


@router.get("/clientes")
def clientes(pool: Pool) -> list[Cliente]:
    return listar_clientes(pool)


@router.get("/pedidos")
def pedidos(pool: Pool, cliente_id: ClienteId) -> list[PedidoDoCliente]:
    return [
        PedidoDoCliente(**{**vars(pedido), "valor": float(pedido.valor)})
        for pedido in StoreDePedidosPostgres(pool).listar(cliente_id)
    ]


@router.post("/conversas", status_code=201)
def criar(conn: Conexao, cliente_id: ClienteId, corpo: NovaConversa | None = None) -> dict:
    return {"id": criar_conversa(conn, cliente_id, corpo.titulo if corpo else None)}


@router.get("/conversas")
def listar(conn: Conexao, cliente_id: ClienteId) -> list[Conversa]:
    return listar_conversas(conn, cliente_id)


@router.get("/conversas/{conversa_id}")
def detalhe(conn: Conexao, cliente_id: ClienteId, conversa_id: str) -> Conversa:
    return conversa_do_cliente(conn, conversa_id, cliente_id)


@router.post("/conversas/{conversa_id}/mensagens", status_code=202)
def enviar(
    conn: Conexao, cliente_id: ClienteId, conversa_id: str, corpo: NovaMensagem
) -> MensagemRecebida:
    conversa = conversa_do_cliente(conn, conversa_id, cliente_id)
    if conversa.status == "aprovacao_pendente":
        # Uma mensagem nova desmontaria a interrupção do grafo que espera o Atendente.
        raise HTTPException(
            status_code=409, detail="A Conversa aguarda a decisão de um Atendente sobre o Reembolso"
        )
    conteudo = mascarar(corpo.conteudo.strip())
    enfileirada = enfileirar_mensagem(conn, conversa.id, corpo.message_id, conteudo, cliente_id)
    return MensagemRecebida(enfileirada=enfileirada, conteudo=conteudo)


@router.get("/conversas/{conversa_id}/mensagens")
def mensagens(conn: Conexao, cliente_id: ClienteId, conversa_id: str) -> list[Mensagem]:
    conversa = conversa_do_cliente(conn, conversa_id, cliente_id)
    return listar_mensagens(conn, conversa.id)
