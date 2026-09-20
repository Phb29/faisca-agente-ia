# Uma imagem para a api e o worker; o que muda é o comando (ver docker-compose.yml).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    FASTEMBED_CACHE_PATH=/app/.cache/fastembed

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

# Dependências primeiro, para o cache do Docker aproveitar builds seguintes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# Os pesos do MiniLM, do BM25 e do ColBERT são baixados no build, não no startup,
# para o worker no Railway subir rápido.
RUN uv run python -c "from ampere.rag.indice import baixar_modelos; baixar_modelos()"

ENV PATH="/app/.venv/bin:$PATH" PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn ampere.api.app:app --host 0.0.0.0 --port ${PORT}"]
