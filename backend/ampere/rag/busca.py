"""Retriever: busca híbrida numa única chamada da Query API do Qdrant.

Dois prefetches (denso e BM25, com o mesmo filtro de payload) são fundidos por RRF.
Com reranker ColBERT, a fusão vira um prefetch intermediário e o query principal é o
multivetor ColBERT da pergunta (MaxSim). Se o self-querying gerar um filtro que devolve
menos que `minimo_candidatos`, a busca roda de novo sem filtro.
"""

from typing import Any, Literal, Protocol

from qdrant_client import QdrantClient, models

from ampere.rag.chunkers import Chunk
from ampere.rag.embedders import Embedder
from ampere.rag.filtro import FiltroDeBusca, traduzir_filtro
from ampere.rag.indice import (
    NOME_VETOR_COLBERT,
    NOME_VETOR_DENSO,
    NOME_VETOR_ESPARSO,
    modelo_bm25,
    modelo_colbert,
    vetor_esparso,
)
from ampere.rag.self_querying import SelfQuerying

Reranker = Literal["colbert", "nenhum"]


class Retriever(Protocol):
    def buscar(self, pergunta: str, *, k: int = 5) -> list[Chunk]: ...


class RetrieverFalso:
    """Devolve sempre a mesma lista e guarda as perguntas recebidas."""

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = list(chunks)
        self.perguntas: list[str] = []

    def buscar(self, pergunta: str, *, k: int = 5) -> list[Chunk]:
        self.perguntas.append(pergunta)
        return self.chunks[:k]


class RetrieverQdrant:
    def __init__(
        self,
        client: QdrantClient,
        colecao: str,
        embedder: Embedder,
        *,
        reranker: Reranker = "colbert",
        self_querying: SelfQuerying | None = None,
        minimo_candidatos: int = 3,
        candidatos_por_prefetch: int = 20,
    ) -> None:
        self.client = client
        self.colecao = colecao
        self.embedder = embedder
        self.reranker = reranker
        self.self_querying = self_querying
        self.minimo_candidatos = minimo_candidatos
        self.candidatos_por_prefetch = candidatos_por_prefetch
        self.ultimo_filtro: FiltroDeBusca | None = None

    def buscar(
        self, pergunta: str, *, k: int = 5, filtro: FiltroDeBusca | None = None
    ) -> list[Chunk]:
        """`filtro` explícito tem precedência; sem ele, o self-querying gera um (se houver)."""
        if filtro is None and self.self_querying is not None:
            filtro = self.self_querying.gerar_filtro(pergunta)
        condicao = traduzir_filtro(filtro)
        self.ultimo_filtro = filtro if condicao is not None else None
        resultados = self._consultar(pergunta, k, condicao)
        if condicao is not None and len(resultados) < self.minimo_candidatos:
            self.ultimo_filtro = None
            resultados = self._consultar(pergunta, k, None)
        return resultados

    def _consultar(self, pergunta: str, k: int, filtro: models.Filter | None) -> list[Chunk]:
        denso = models.Prefetch(
            query=self.embedder.embed([pergunta])[0],
            using=NOME_VETOR_DENSO,
            filter=filtro,
            limit=self.candidatos_por_prefetch,
        )
        esparso = models.Prefetch(
            query=vetor_esparso(next(iter(modelo_bm25().query_embed(pergunta)))),
            using=NOME_VETOR_ESPARSO,
            filter=filtro,
            limit=self.candidatos_por_prefetch,
        )
        fusao = models.FusionQuery(fusion=models.Fusion.RRF)
        parametros: dict[str, Any]
        if self.reranker == "colbert":
            fundido = models.Prefetch(
                prefetch=[denso, esparso], query=fusao, limit=self.candidatos_por_prefetch
            )
            multivetor = next(iter(modelo_colbert().query_embed(pergunta))).tolist()
            parametros = {
                "prefetch": fundido,
                "query": multivetor,
                "using": NOME_VETOR_COLBERT,
                "query_filter": filtro,
            }
        else:
            parametros = {"prefetch": [denso, esparso], "query": fusao}
        resposta = self.client.query_points(
            collection_name=self.colecao, limit=k, with_payload=True, **parametros
        )
        return [self._chunk(ponto) for ponto in resposta.points]

    @staticmethod
    def _chunk(ponto: models.ScoredPoint) -> Chunk:
        payload = dict(ponto.payload or {})
        payload["score"] = float(ponto.score)
        return Chunk.model_validate(payload)
