"""Rotas do login: entrar, sair e quem está na sessão.

O navegador não fala com a api: o frontend repassa cada chamada, guarda o token num cookie
`HttpOnly` dele e o manda aqui como `Authorization: Bearer`, junto com o IP do navegador em
`X-Ip-Do-Cliente` (ver docs/superpowers/specs/2026-10-16-login.md). A senha nunca vai para o
log.
"""

import hmac
import math
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ampere.acesso.senha import HASH_FIXO, conferir
from ampere.acesso.sessoes import criar_sessao, encerrar_sessao, limpar_expiradas
from ampere.acesso.tentativas import bloqueio, limpar_antigas, normalizar, registrar
from ampere.api.dependencias import Conexao, Configuracao, IpDoCliente, SessaoAtual, TokenDaSessao
from ampere.nucleo.config import Config

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


@router.post("/entrar")
def entrar(
    corpo: Credenciais, request: Request, conn: Conexao, config: Configuracao, ip: IpDoCliente
) -> SessaoAberta:
    """Primeiro o bloqueio: com tentativas demais, 429 sem registrar tentativa nova. Depois
    e-mail e senha, com a mesma resposta (e o mesmo tempo) para os dois errados."""
    email = normalizar(corpo.email)
    espera = bloqueio(conn, email, ip)
    if espera is not None:
        raise HTTPException(
            status_code=429,
            detail=f"Muitas tentativas. Tente de novo em {_minutos(espera)}.",
            headers={"Retry-After": str(espera)},
        )
    certo = _credenciais_conferem(config, email, corpo.senha)
    registrar(conn, email, ip, certo)
    limpar_expiradas(conn)
    limpar_antigas(conn)
    if not certo:
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    user_agent = request.headers.get("user-agent", "")[:300]
    token, expira_em = criar_sessao(
        conn, email, horas=config.sessao_horas, ip=ip, user_agent=user_agent
    )
    return SessaoAberta(token=token, email=email, expira_em=expira_em)


@router.post("/sair", status_code=204)
def sair(conn: Conexao, token: TokenDaSessao) -> Response:
    """Encerra a sessão do Bearer. Sem Bearer, ou com a sessão já encerrada, também é 204:
    sair duas vezes não é erro."""
    if token:
        encerrar_sessao(conn, token)
    return Response(status_code=204)


@router.get("/eu")
def eu(sessao: SessaoAtual) -> QuemEsta:
    return QuemEsta(email=sessao.email, expira_em=sessao.expira_em)


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
