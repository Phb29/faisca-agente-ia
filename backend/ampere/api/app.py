"""Fábrica do app FastAPI. `criar_app(config, ...)` monta as rotas de Cliente, de Atendente
e o SSE; `app` no fim do módulo serve o `uvicorn ampere.api.app:app`."""

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ampere.api import atendente, cliente, sse
from ampere.api.atendente import MemoriaProcedural
from ampere.nucleo.banco import conectar
from ampere.nucleo.config import Config


def _postgres_responde(config: Config) -> bool:
    try:
        with conectar(config.database_url) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001 - health check só diz se respondeu
        return False


def _qdrant_responde(config: Config) -> bool:
    try:
        from qdrant_client import QdrantClient

        QdrantClient(url=config.qdrant_url).get_collections()
        return True
    except Exception:  # noqa: BLE001
        return False


def criar_app(
    config: Config,
    *,
    memoria_procedural: MemoriaProcedural | None = None,
    verificar_qdrant: Callable[[], bool] | None = None,
) -> FastAPI:
    app = FastAPI(title="Suporte Ampère", version="0.1.0")
    app.state.config = config
    app.state.memoria_procedural = memoria_procedural
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> JSONResponse:
        postgres = _postgres_responde(config)
        qdrant = verificar_qdrant() if verificar_qdrant else _qdrant_responde(config)
        ok = postgres and qdrant
        return JSONResponse(
            {"status": "ok" if ok else "erro", "postgres": postgres, "qdrant": qdrant},
            status_code=200 if ok else 503,
        )

    app.include_router(cliente.router)
    app.include_router(sse.router)
    app.include_router(atendente.router)
    return app
