"""Dependências de segurança e de infraestrutura das rotas: quem é o Cliente, se o token
do Atendente confere, e uma conexão com o banco por request."""

import uuid
from collections.abc import Iterator
from typing import Annotated

import psycopg
from fastapi import Depends, Header, HTTPException, Query, Request

from ampere.nucleo.banco import conectar
from ampere.nucleo.config import Config


def obter_config(request: Request) -> Config:
    return request.app.state.config


def conexao(config: Annotated[Config, Depends(obter_config)]) -> Iterator[psycopg.Connection]:
    """Uma conexão por request: commita ao sair sem erro, desfaz com erro, e fecha."""
    with conectar(config.database_url) as conn:
        yield conn


def cliente_atual(
    x_cliente_id: Annotated[str | None, Header()] = None,
    cliente_id: Annotated[str | None, Query()] = None,
) -> str:
    """Identifica o Cliente pelo header `X-Cliente-Id` ou, na falta dele, pela query string
    `cliente_id` (o EventSource do navegador não envia headers). Sem autenticação de
    verdade, de propósito: está fora do escopo."""
    valor = (x_cliente_id or cliente_id or "").strip()
    if not valor:
        raise HTTPException(status_code=400, detail="informe X-Cliente-Id ou ?cliente_id=")
    return valor


def exigir_atendente(
    config: Annotated[Config, Depends(obter_config)],
    x_atendente_token: Annotated[str | None, Header()] = None,
) -> None:
    if x_atendente_token != config.atendente_token:
        raise HTTPException(status_code=401, detail="token de Atendente inválido")


def uuid_ou_404(valor: str) -> str:
    """Ids inválidos viram 404 em vez de erro do Postgres."""
    try:
        return str(uuid.UUID(valor))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="não encontrado") from exc


Conexao = Annotated[psycopg.Connection, Depends(conexao)]
ClienteId = Annotated[str, Depends(cliente_atual)]
