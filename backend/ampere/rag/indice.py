"""Coleções do Qdrant: três vetores nomeados por ponto (denso, esparso BM25, multivetor ColBERT),
índices de payload nos quatro metadados e upsert de chunks em lotes."""

import uuid
from datetime import date
from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient, models

from ampere.rag.chunkers import Chunk
from ampere.rag.embedders import Embedder

NOME_VETOR_DENSO = "denso"
NOME_VETOR_COLBERT = "colbert"
NOME_VETOR_ESPARSO = "bm25"

MODELO_BM25 = "Qdrant/bm25"
MODELO_COLBERT = "answerdotai/answerai-colbert-small-v1"
DIMS_COLBERT = 96

TAMANHO_DO_LOTE = 64
NAMESPACE_PONTOS = uuid.UUID("6f1c0a2e-3b7d-4c8e-9f10-a1b2c3d4e5f6")


@lru_cache
def modelo_bm25() -> Any:
    from fastembed import SparseTextEmbedding

    return SparseTextEmbedding(MODELO_BM25)


@lru_cache
def modelo_colbert() -> Any:
    from fastembed import LateInteractionTextEmbedding

    return LateInteractionTextEmbedding(MODELO_COLBERT)


def baixar_modelos() -> None:
    """Força o download dos três modelos fastembed; usado no build da imagem Docker."""
    from ampere.rag.embedders import EmbedderMiniLM

    EmbedderMiniLM().embed(["aquecimento"])
    list(modelo_bm25().embed(["aquecimento"]))
    list(modelo_colbert().embed(["aquecimento"]))


def criar_colecao(client: QdrantClient, nome: str, dims: int, *, recriar: bool = False) -> None:
    if client.collection_exists(nome):
        if not recriar:
            return
        client.delete_collection(nome)
    client.create_collection(
        collection_name=nome,
        vectors_config={
            NOME_VETOR_DENSO: models.VectorParams(size=dims, distance=models.Distance.COSINE),
            NOME_VETOR_COLBERT: models.VectorParams(
                size=DIMS_COLBERT,
                distance=models.Distance.COSINE,
                multivector_config=models.MultiVectorConfig(
                    comparator=models.MultiVectorComparator.MAX_SIM
                ),
                hnsw_config=models.HnswConfigDiff(m=0),
            ),
        },
        sparse_vectors_config={
            NOME_VETOR_ESPARSO: models.SparseVectorParams(modifier=models.Modifier.IDF)
        },
    )
    for campo in ("categoria", "produto", "tipo"):
        client.create_payload_index(nome, campo, models.PayloadSchemaType.KEYWORD)
    client.create_payload_index(nome, "vigencia", models.PayloadSchemaType.DATETIME)


def id_do_ponto(documento: str, indice: int) -> str:
    return str(uuid.uuid5(NAMESPACE_PONTOS, f"{documento}:{indice}"))


def vigencia_iso(vigencia: str) -> str:
    """ "2026-01-01" -> "2026-01-01T00:00:00Z", o formato que o índice DATETIME entende."""
    if "T" in vigencia:
        return vigencia
    return f"{date.fromisoformat(vigencia).isoformat()}T00:00:00Z"


def vetor_esparso(embedding: Any) -> models.SparseVector:
    objeto = embedding.as_object()
    return models.SparseVector(
        indices=[int(i) for i in objeto["indices"]],
        values=[float(v) for v in objeto["values"]],
    )


def indexar_chunks(
    client: QdrantClient,
    nome_colecao: str,
    chunks: list[Chunk],
    embedder: Embedder,
    *,
    com_colbert: bool = True,
) -> int:
    total = 0
    for inicio in range(0, len(chunks), TAMANHO_DO_LOTE):
        lote = chunks[inicio : inicio + TAMANHO_DO_LOTE]
        textos = [c.texto for c in lote]
        densos = embedder.embed(textos)
        esparsos = list(modelo_bm25().embed(textos))
        colberts = list(modelo_colbert().embed(textos)) if com_colbert else [None] * len(lote)
        pontos = []
        for chunk, denso, esparso, colbert in zip(lote, densos, esparsos, colberts, strict=True):
            vetores: dict[str, Any] = {
                NOME_VETOR_DENSO: denso,
                NOME_VETOR_ESPARSO: vetor_esparso(esparso),
            }
            if colbert is not None:
                vetores[NOME_VETOR_COLBERT] = colbert.tolist()
            payload = chunk.model_dump(exclude={"score"})
            payload["vigencia"] = vigencia_iso(chunk.vigencia)
            pontos.append(
                models.PointStruct(
                    id=id_do_ponto(chunk.documento, chunk.indice), vector=vetores, payload=payload
                )
            )
        client.upsert(nome_colecao, pontos, wait=True)
        total += len(pontos)
    return total
