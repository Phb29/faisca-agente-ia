"""Configuração única do sistema, lida do ambiente ou de um arquivo .env."""

from functools import cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Provedor = Literal["openai", "groq"]


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Infraestrutura
    database_url: str = "postgresql://ampere:ampere@localhost:5439/ampere"
    qdrant_url: str = "http://localhost:6333"
    origens_permitidas: list[str] = ["*"]

    # Chaves (ausentes = recurso desligado ou falso)
    openai_api_key: str | None = None
    groq_api_key: str | None = None
    typesafe_api_key: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"

    # Modelos (ver docs/adr/0002 e 0008): cada papel tem um provedor e um modelo
    modelos_falsos: bool = False
    provedor_gerador: Provedor = "openai"
    modelo_gerador: str = "gpt-5.6-terra"
    provedor_juiz: Provedor = "openai"
    modelo_juiz: str = "gpt-5.6-sol"
    provedor_trabalhador: Provedor = "groq"
    modelo_trabalhador: str = "openai/gpt-oss-120b"

    # RAG (ver docs/adr/0003)
    embedder: Literal["minilm", "openai"] = "minilm"
    chunker: Literal["recursivo", "markdown", "semantico"] = "markdown"
    reranker: Literal["colbert", "nenhum"] = "colbert"
    self_querying: bool = True
    minimo_candidatos_filtrados: int = 3

    # Limiares do Jev e política de Reembolso (ver ampere/regras)
    limiar_guardrail_entrada: float = 0.7
    limiar_dado_sensivel: float = 0.5
    limiar_guardrail_saida: float = 0.7
    limiar_gate_aprovacao: float = 0.5
    valor_limite_reembolso: float = 300.0
    janela_reembolso_recente_dias: int = 30

    # Streaming: com true, o Cliente vê a resposta sendo escrita antes do Guardrail de saída
    # aprovar (e o front apaga o rascunho se ela for reprovada); com false, nada sai antes.
    tokens_antes_do_guardrail: bool = True

    # Memória de Curto Prazo: acima disto, as mensagens antigas viram resumo
    limite_mensagens_resumo: int = 20

    # Tela do Atendente
    atendente_token: str = "atendente-secreto"


@cache
def config() -> Config:
    """Instância única lida do ambiente. Testes constroem `Config(...)` diretamente."""
    return Config()
