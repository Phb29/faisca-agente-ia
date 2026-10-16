"""Fábrica do app FastAPI. `criar_app` recebe tudo de fora (configuração, pool, Memória
Procedural), então quem monta de verdade é a raiz de composição (`ampere/cli.py`) e os
testes montam com o que quiserem.

Toda rota exige uma sessão de login, menos `/health` e as de entrar e sair: cada router
declara a exigência (`exigir_sessao`) nas próprias dependências. Pool sem conexão livre vira
503 rápido, com `Retry-After`, e não um 500 depois de muito tempo parado."""

import logging
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import ConnectionPool, PoolTimeout
from qdrant_client import QdrantClient

from ampere.api import acesso, atendente, avaliacao, cliente, sse
from ampere.api.atendente import MemoriaProcedural
from ampere.nucleo.config import Config

VerificacaoDeSaude = Callable[[], bool]

logger = logging.getLogger(__name__)


def criar_app(
    config: Config,
    *,
    pool: ConnectionPool,
    memoria_procedural: MemoriaProcedural | None = None,
    verificar_qdrant: VerificacaoDeSaude | None = None,
) -> FastAPI:
    app = FastAPI(title="Suporte Ampère", version="0.2.0")
    app.state.config = config
    app.state.pool = pool
    app.state.memoria_procedural = memoria_procedural
    app.state.vez_do_login = acesso.nova_vez_do_login()
    app.add_exception_handler(PoolTimeout, _banco_ocupado)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.origens_permitidas,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    verificar_postgres = _postgres_responde(pool)
    verificar_qdrant = verificar_qdrant or _qdrant_responde(config.qdrant_url)

    @app.get("/health")
    def health() -> JSONResponse:
        postgres, qdrant = verificar_postgres(), verificar_qdrant()
        ok = postgres and qdrant
        return JSONResponse(
            {"status": "ok" if ok else "erro", "postgres": postgres, "qdrant": qdrant},
            status_code=200 if ok else 503,
        )

    if not (config.login_email.strip() and config.login_senha_hash.strip()):
        logger.warning(
            "Login desligado: sem LOGIN_EMAIL e LOGIN_SENHA_HASH, ninguém entra. "
            "Gere o hash com `ampere hash-senha`."
        )

    app.include_router(acesso.router)
    app.include_router(cliente.router)
    app.include_router(sse.router)
    app.include_router(atendente.router)
    app.include_router(avaliacao.router)
    return app


async def _banco_ocupado(request: Request, _exc: Exception) -> JSONResponse:
    logger.warning("pool do Postgres sem conexão livre em %s %s", request.method, request.url.path)
    return JSONResponse(
        {"detail": "Banco ocupado. Tente de novo em instantes."},
        status_code=503,
        headers={"Retry-After": "1"},
    )


def _postgres_responde(pool: ConnectionPool) -> VerificacaoDeSaude:
    def verificar() -> bool:
        try:
            with pool.connection(timeout=3) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001 - health check só diz se respondeu
            return False

    return verificar


def _qdrant_responde(url: str) -> VerificacaoDeSaude:
    def verificar() -> bool:
        try:
            QdrantClient(url=url, timeout=3).get_collections()
            return True
        except Exception:  # noqa: BLE001
            return False

    return verificar
