"""Dependências das rotas: configuração, conexão com o banco, a sessão de quem chama, o IP do
navegador e qual Cliente de exemplo o chat representa.

As que só leem o request são `async`: rodam no laço de eventos, sem ocupar uma thread. As que
falam com o banco esperam no máximo `ESPERA_POR_CONEXAO` segundos por uma conexão livre; sem
ela, o `PoolTimeout` vira 503 em `criar_app`, em vez de deixar o request parado."""

import uuid
from collections.abc import Iterator
from typing import Annotated

import psycopg
from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg_pool import ConnectionPool

from ampere.acesso.sessoes import Sessao, marca_da_credencial, sessao_valida
from ampere.nucleo.config import Config

_bearer = HTTPBearer(auto_error=False, description="Token devolvido por POST /acesso/entrar.")

ESPERA_POR_CONEXAO = 5.0  # segundos


async def obter_config(request: Request) -> Config:
    return request.app.state.config


async def obter_pool(request: Request) -> ConnectionPool:
    return request.app.state.pool


Configuracao = Annotated[Config, Depends(obter_config)]
Pool = Annotated[ConnectionPool, Depends(obter_pool)]


def conexao(pool: Pool) -> Iterator[psycopg.Connection]:
    """Uma conexão do pool por request, em autocommit; transações são explícitas."""
    with pool.connection(timeout=ESPERA_POR_CONEXAO) as conn:
        yield conn


async def token_da_sessao(
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str | None:
    """O token do cabeçalho `Authorization: Bearer <token>`, ou None. A api não lê cookie: quem
    guarda o token é o frontend, num cookie dele, e o repassa neste cabeçalho."""
    return credenciais.credentials if credenciais else None


def credencial_atual(config: Config) -> str:
    """A marca da conta configurada agora. Sessão aberta com outra marca não vale."""
    return marca_da_credencial(config.login_email, config.login_senha_hash)


def exigir_sessao(
    pool: Pool, config: Configuracao, token: Annotated[str | None, Depends(token_da_sessao)]
) -> Sessao:
    """A sessão de quem chama, ou 401. Lê numa conexão própria, devolvida na hora, e não na
    `conexao` do request, que numa rota de stream ficaria presa enquanto o stream durasse.
    Sessão aberta antes de trocarem a senha ou o e-mail da conta também dá 401."""
    sessao = None
    if token:
        with pool.connection(timeout=ESPERA_POR_CONEXAO) as conn:
            sessao = sessao_valida(conn, token, credencial=credencial_atual(config))
    if sessao is None:
        raise HTTPException(
            status_code=401,
            detail="Sessão inválida ou expirada.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return sessao


async def ip_do_cliente(
    request: Request, x_ip_do_cliente: Annotated[str | None, Header()] = None
) -> str:
    """O IP do navegador, para o limite de tentativas. Vem do `X-Ip-Do-Cliente`, que o frontend
    monta a partir do `X-Forwarded-For` do Railway; a api só confia nele porque não tem
    endereço público. Sem o cabeçalho, vale o IP da conexão."""
    ip = (x_ip_do_cliente or "").split(",")[0].strip()
    if not ip and request.client:
        ip = request.client.host
    return ip[:64] or "desconhecido"


def cliente_atual(
    x_cliente_id: Annotated[str | None, Header()] = None,
    cliente_id: Annotated[str | None, Query()] = None,
) -> str:
    """O Cliente de exemplo que o chat representa vem do header `X-Cliente-Id` ou, na falta
    dele, da query `cliente_id` (o EventSource do navegador não envia headers). Não é
    autenticação: quem pode usar o sistema é decidido pela sessão."""
    valor = (x_cliente_id or cliente_id or "").strip()
    if not valor:
        raise HTTPException(status_code=400, detail="informe X-Cliente-Id ou ?cliente_id=")
    return valor


def uuid_ou_404(valor: str) -> str:
    """Id malformado vira 404, e não um erro do Postgres."""
    try:
        return str(uuid.UUID(valor))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="não encontrado") from exc


Conexao = Annotated[psycopg.Connection, Depends(conexao)]
TokenDaSessao = Annotated[str | None, Depends(token_da_sessao)]
SessaoAtual = Annotated[Sessao, Depends(exigir_sessao)]
IpDoCliente = Annotated[str, Depends(ip_do_cliente)]
ClienteId = Annotated[str, Depends(cliente_atual)]
