# Backend

Backend Python do chatbot da Ampère, organizado por conceito de domínio (ver `docs/adr/0005`). Cada pasta de `ampere/` corresponde a um termo do glossário em `CONTEXT.md` e tem um README de um parágrafo. O grafo importa das outras pastas; nenhuma outra importa do grafo.

Como rodar: `uv sync`, `uv run pytest` (unitários e grafo não precisam de nada), `uv run pytest -m integracao` com `DATABASE_URL` e `QDRANT_URL` apontando para o docker-compose.
