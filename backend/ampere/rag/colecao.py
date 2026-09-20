"""Nome das coleções do Qdrant: uma por combinação de embedder e chunker."""

from itertools import product

PREFIXO = "politicas"
EMBEDDERS = ("minilm", "openai")
CHUNKERS = ("recursivo", "markdown", "semantico")


def nome_da_colecao(embedder: str, chunker: str) -> str:
    return f"{PREFIXO}__{embedder}__{chunker}"


def todas_as_combinacoes() -> list[tuple[str, str]]:
    return list(product(EMBEDDERS, CHUNKERS))
