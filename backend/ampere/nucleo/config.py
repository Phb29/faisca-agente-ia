"""Configuração única do sistema, lida do ambiente ou de um arquivo .env."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://ampere:ampere@localhost:5439/ampere"
    qdrant_url: str = "http://localhost:6333"

    openai_api_key: str | None = None
    groq_api_key: str | None = None
    typesafe_api_key: str | None = None

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    modelos_falsos: bool = False
    modelo_gerador: str = "gpt-5.6-terra"
    modelo_juiz: str = "gpt-5.6-sol"
    modelo_trabalhador: str = "openai/gpt-oss-120b"

    embedder: Literal["minilm", "openai"] = "minilm"
    chunker: Literal["recursivo", "markdown", "semantico"] = "markdown"
    reranker: Literal["colbert", "nenhum"] = "colbert"
    self_querying: bool = True
    minimo_candidatos_filtrados: int = 3

    limiar_guardrail_entrada: float = 0.7
    limiar_guardrail_saida: float = 0.7
    limiar_gate_aprovacao: float = 0.5
    valor_limite_reembolso: float = 300.0
    janela_reembolso_recente_dias: int = 30

    limite_mensagens_resumo: int = 20

    atendente_token: str = "atendente-secreto"


@lru_cache
def config() -> Config:
    """Instância única lida do ambiente. Testes constroem `Config(...)` diretamente."""
    return Config()
