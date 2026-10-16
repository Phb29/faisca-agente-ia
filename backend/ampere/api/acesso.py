"""Rotas do login: entrar, sair e quem está na sessão.

O navegador não fala com a api: o frontend repassa cada chamada, guarda o token num cookie
`HttpOnly` dele e o manda aqui como `Authorization: Bearer`, junto com o IP do navegador em
`X-Ip-Do-Cliente` (ver docs/superpowers/specs/2026-10-16-login.md). A senha nunca vai para o
log.

`entrar` é assíncrona de propósito. Cada scrypt usa 32 MiB e leva perto de um décimo de
segundo, então só `LOGINS_SIMULTANEOS` logins correm juntos por processo. Quem não consegue a
vez em `ESPERA_PELA_VEZ` segundos recebe 503 sem ter tocado no banco nem ocupado uma thread.
Dentro da vez, o banco é usado em passos curtos, cada um com a própria conexão, e o scrypt
roda sem conexão nenhuma na mão. Assim uma rajada de logins não esgota o pool nem as threads
da api, e as outras rotas continuam respondendo.
"""

import asyncio
import hmac
import math
from collections.abc import Callable
from datetime import datetime

import psycopg
from fastapi import APIRouter, HTTPException, Request, Response
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ampere.acesso.senha import HASH_FIXO, conferir
from ampere.acesso.sessoes import criar_sessao, encerrar_sessao, limpar_expiradas
from ampere.acesso.tentativas import (
    Bloqueado,
    comecar,
    limpar_antigas,
    marcar_sucesso,
    normalizar,
)
from ampere.api.dependencias import (
    Configuracao,
    IpDoCliente,
    Pool,
    SessaoAtual,
    TokenDaSessao,
    credencial_atual,
)
from ampere.nucleo.config import Config

LOGINS_SIMULTANEOS = 4
ESPERA_PELA_VEZ = 1.0  # segundos
ESPERA_POR_CONEXAO = 2.0  # segundos

router = APIRouter(prefix="/acesso")


class Credenciais(BaseModel):
    email: str = Field(max_length=320)
    senha: str = Field(max_length=1024)


class SessaoAberta(BaseModel):
    token: str
    email: str
    expira_em: datetime


class QuemEsta(BaseModel):
    email: str
    expira_em: datetime


def nova_vez_do_login() -> asyncio.Semaphore:
    """As vagas de login de um app. Fica no `app.state`, uma por app (e por processo), e não
    no módulo: um semáforo do asyncio se prende ao primeiro laço de eventos que espera nele."""
    return asyncio.Semaphore(LOGINS_SIMULTANEOS)


@router.post("/entrar")
async def entrar(
    corpo: Credenciais, request: Request, pool: Pool, config: Configuracao, ip: IpDoCliente
) -> SessaoAberta:
    """Primeiro a vez. Depois a tentativa entra no banco como falha e a janela é contada com
    ela: com tentativas demais, 429, e a tentativa é apagada. Depois e-mail e senha, com a
    mesma resposta (e o mesmo tempo) para os dois errados. Só o login certo volta ao banco:
    marca o sucesso, abre a sessão e aproveita para limpar o que passou da validade."""
    vez: asyncio.Semaphore = request.app.state.vez_do_login
    try:
        await asyncio.wait_for(vez.acquire(), ESPERA_PELA_VEZ)
    except TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Muitas tentativas agora. Tente de novo em instantes.",
            headers={"Retry-After": "1"},
        ) from None
    try:
        user_agent = request.headers.get("user-agent", "")[:300]
        return await _entrar(pool, config, normalizar(corpo.email), corpo.senha, ip, user_agent)
    finally:
        vez.release()


@router.post("/sair", status_code=204)
async def sair(pool: Pool, token: TokenDaSessao) -> Response:
    """Encerra a sessão do Bearer. Sem Bearer, ou com a sessão já encerrada, também é 204:
    sair duas vezes não é erro."""
    if token:
        await _no_banco(pool, encerrar_sessao, token)
    return Response(status_code=204)


@router.get("/eu")
async def eu(sessao: SessaoAtual) -> QuemEsta:
    return QuemEsta(email=sessao.email, expira_em=sessao.expira_em)


async def _entrar(
    pool: ConnectionPool, config: Config, email: str, senha: str, ip: str, user_agent: str
) -> SessaoAberta:
    try:
        tentativa = await _no_banco(pool, comecar, email, ip)
    except Bloqueado as bloqueado:
        raise HTTPException(
            status_code=429,
            detail=f"Muitas tentativas. Tente de novo em {_minutos(bloqueado.segundos)}.",
            headers={"Retry-After": str(bloqueado.segundos)},
        ) from None
    if not await run_in_threadpool(_credenciais_conferem, config, email, senha):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    token, expira_em = await _no_banco(
        pool, _abrir_sessao, tentativa, email, config, ip, user_agent
    )
    return SessaoAberta(token=token, email=email, expira_em=expira_em)


def _abrir_sessao(
    conn: psycopg.Connection, tentativa: int, email: str, config: Config, ip: str, user_agent: str
) -> tuple[str, datetime]:
    credencial, horas = credencial_atual(config), config.sessao_horas
    with conn.transaction():
        marcar_sucesso(conn, tentativa)
        aberta = criar_sessao(
            conn, email, credencial=credencial, horas=horas, ip=ip, user_agent=user_agent
        )
    limpar_expiradas(conn)
    limpar_antigas(conn)
    return aberta


async def _no_banco[T](pool: ConnectionPool, passo: Callable[..., T], *args, **kwargs) -> T:
    """Roda um passo curto numa thread, com uma conexão pega só para ele e devolvida logo
    depois. Sem conexão livre em `ESPERA_POR_CONEXAO` segundos, o `PoolTimeout` vira 503."""

    def rodar() -> T:
        with pool.connection(timeout=ESPERA_POR_CONEXAO) as conn:
            return passo(conn, *args, **kwargs)

    return await run_in_threadpool(rodar)


def _credenciais_conferem(config: Config, email: str, senha: str) -> bool:
    """Só a conta configurada entra. Com outro e-mail, ou sem conta configurada, a senha passa
    pelo scrypt mesmo assim, contra um hash fixo, para o tempo de resposta não revelar se o
    e-mail existe."""
    conta = normalizar(config.login_email)
    if conta and config.login_senha_hash and hmac.compare_digest(email.encode(), conta.encode()):
        return conferir(senha, config.login_senha_hash)
    conferir(senha, HASH_FIXO)
    return False


def _minutos(segundos: int) -> str:
    minutos = math.ceil(segundos / 60)
    return "1 minuto" if minutos == 1 else f"{minutos} minutos"
