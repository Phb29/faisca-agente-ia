"""Fábrica do app FastAPI. `criar_app` recebe tudo de fora (configuração, pool, Memória
Procedural), então quem monta de verdade é a raiz de composição (`ampere/cli.py`) e os
testes montam com o que quiserem."""

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import ConnectionPool
from qdrant_client import QdrantClient

from ampere.api import atendente, avaliacao, cliente, sse
from ampere.api.atendente import MemoriaProcedural
from ampere.nucleo.config import Config

VerificacaoDeSaude = Callable[[], bool]


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

    app.include_router(cliente.router)
    app.include_router(sse.router)
    app.include_router(atendente.router)
    app.include_router(avaliacao.router)
    return app


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
