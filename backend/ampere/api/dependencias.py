"""Dependências das rotas: configuração, conexão com o banco, quem é o Cliente e se o token
do Atendente confere."""

import secrets
import uuid
from collections.abc import Iterator
from typing import Annotated

import psycopg
from fastapi import Depends, Header, HTTPException, Query, Request
from psycopg_pool import ConnectionPool

from ampere.nucleo.config import Config


def obter_config(request: Request) -> Config:
    return request.app.state.config


def obter_pool(request: Request) -> ConnectionPool:
    return request.app.state.pool


def conexao(pool: Annotated[ConnectionPool, Depends(obter_pool)]) -> Iterator[psycopg.Connection]:
    """Uma conexão do pool por request, em autocommit; transações são explícitas."""
    with pool.connection() as conn:
        yield conn


def cliente_atual(
    x_cliente_id: Annotated[str | None, Header()] = None,
    cliente_id: Annotated[str | None, Query()] = None,
) -> str:
    """O Cliente vem do header `X-Cliente-Id` ou, na falta dele, da query `cliente_id` (o
    EventSource do navegador não envia headers). Não há autenticação de verdade, de
    propósito: está fora do escopo do projeto."""
    valor = (x_cliente_id or cliente_id or "").strip()
    if not valor:
        raise HTTPException(status_code=400, detail="informe X-Cliente-Id ou ?cliente_id=")
    return valor


def exigir_atendente(
    config: Annotated[Config, Depends(obter_config)],
    x_atendente_token: Annotated[str | None, Header()] = None,
) -> None:
    """Comparação em tempo constante, para o tempo de resposta não vazar o token."""
    recebido = (x_atendente_token or "").encode()
    if not secrets.compare_digest(recebido, config.atendente_token.encode()):
        raise HTTPException(status_code=401, detail="token de Atendente inválido")


def uuid_ou_404(valor: str) -> str:
    """Id malformado vira 404, e não um erro do Postgres."""
    try:
        return str(uuid.UUID(valor))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="não encontrado") from exc


Configuracao = Annotated[Config, Depends(obter_config)]
Pool = Annotated[ConnectionPool, Depends(obter_pool)]
Conexao = Annotated[psycopg.Connection, Depends(conexao)]
ClienteId = Annotated[str, Depends(cliente_atual)]
