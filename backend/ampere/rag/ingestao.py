"""Ingestão: lê a Base de Conhecimento, divide, cria a coleção da variante e indexa."""

from pathlib import Path

from qdrant_client import QdrantClient

from ampere.rag.chunkers import Chunker
from ampere.rag.colecao import nome_da_colecao
from ampere.rag.documentos import carregar_documentos
from ampere.rag.embedders import Embedder
from ampere.rag.indice import criar_colecao, indexar_chunks


def ingerir(
    pasta: Path,
    client: QdrantClient,
    embedder: Embedder,
    chunker: Chunker,
    *,
    com_colbert: bool = True,
    recriar: bool = True,
) -> int:
    """Devolve o número de chunks indexados em `nome_da_colecao(embedder.nome, chunker.nome)`."""
    documentos = carregar_documentos(pasta)
    chunks = [chunk for documento in documentos for chunk in chunker.dividir(documento)]
    nome = nome_da_colecao(embedder.nome, chunker.nome)
    criar_colecao(client, nome, embedder.dims, recriar=recriar)
    return indexar_chunks(client, nome, chunks, embedder, com_colbert=com_colbert)
