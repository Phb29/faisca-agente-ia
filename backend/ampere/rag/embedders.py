"""Embedders densos trocáveis por configuração: MiniLM local, OpenAI, ou falso para testes."""

from functools import cache
from typing import Any, Protocol

from ampere.nucleo.config import Config
from ampere.nucleo.falsos import embed_falso

MODELO_MINILM = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODELO_OPENAI = "text-embedding-3-small"


@cache
def _modelo_minilm() -> Any:
    """Uma só cópia do modelo por processo: o retriever, a Memória Semântica e o eval do
    agente criam cada um seu `EmbedderMiniLM`, mas todos carregam o mesmo fastembed."""
    from fastembed import TextEmbedding

    return TextEmbedding(MODELO_MINILM)


class Embedder(Protocol):
    nome: str
    dims: int

    def embed(self, textos: list[str]) -> list[list[float]]: ...


class EmbedderMiniLM:
    """MiniLM multilíngue via fastembed (ONNX, roda na CPU), carregado na primeira chamada."""

    nome = "minilm"
    dims = 384

    def __init__(self) -> None:
        self._modelo: Any = None

    def _carregar(self) -> Any:
        if self._modelo is None:
            self._modelo = _modelo_minilm()
        return self._modelo

    def embed(self, textos: list[str]) -> list[list[float]]:
        if not textos:
            return []
        return [vetor.tolist() for vetor in self._carregar().embed(textos)]


class EmbedderOpenAI:
    nome = "openai"
    dims = 1536

    def __init__(self, api_key: str | None) -> None:
        from langchain_openai import OpenAIEmbeddings

        self._modelo = OpenAIEmbeddings(model=MODELO_OPENAI, api_key=api_key)

    def embed(self, textos: list[str]) -> list[list[float]]:
        if not textos:
            return []
        return self._modelo.embed_documents(textos)


class EmbedderFalso:
    """Mesmo nome e dimensão do MiniLM, para as coleções de teste terem o mesmo nome."""

    nome = "minilm"
    dims = 384

    def embed(self, textos: list[str]) -> list[list[float]]:
        return embed_falso(textos)


def criar_embedder(nome: str, config: Config) -> Embedder:
    if config.modelos_falsos:
        return EmbedderFalso()
    if nome == "minilm":
        return EmbedderMiniLM()
    if nome == "openai":
        return EmbedderOpenAI(api_key=config.openai_api_key)
    raise ValueError(f"Embedder desconhecido: {nome}")
