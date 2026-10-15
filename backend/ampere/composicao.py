"""Raiz de composição: o único lugar que liga configuração, pool, modelos, retriever, stores,
grafo, executor, worker e API.

Fica fora das pastas de conceito de propósito: é aqui que o grafo é entregue à fila (como um
`Executor`) e aos evals (como uma `Composicao`), e que o tipo de job `eval` é ligado à
amostra ao vivo, sem que nenhuma dessas pastas importe da outra (ver docs/adr/0005 e 0009).
"""

from fastapi import FastAPI
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from langgraph.store.postgres import PostgresStore
from psycopg_pool import ConnectionPool
from qdrant_client import QdrantClient

from ampere.acoes.ticket import StoreDeTickets, StoreDeTicketsPostgres
from ampere.api.app import criar_app
from ampere.evals.ao_vivo import ExecutorDeAvaliacao
from ampere.evals.execucoes import RegistroPostgres
from ampere.fila.executor import ExecutorPorTipo
from ampere.grafo.construtor import Dependencias, construir_grafo
from ampere.grafo.executor import ExecutorDoGrafo
from ampere.loja.pedidos import StoreDePedidos, StoreDePedidosPostgres
from ampere.memoria.procedural import MemoriaProcedural
from ampere.memoria.store import criar_store_postgres
from ampere.nucleo.banco import criar_pool
from ampere.nucleo.config import Config
from ampere.nucleo.modelos import FabricaDeModelos
from ampere.observabilidade.langfuse import Observabilidade
from ampere.rag.busca import RetrieverQdrant
from ampere.rag.colecao import nome_da_colecao
from ampere.rag.embedders import criar_embedder
from ampere.rag.self_querying import SelfQuerying


def montar_retriever(cfg: Config, fabrica: FabricaDeModelos) -> RetrieverQdrant:
    embedder = criar_embedder(cfg.embedder, cfg)
    return RetrieverQdrant(
        QdrantClient(url=cfg.qdrant_url),
        nome_da_colecao(embedder.nome, cfg.chunker),
        embedder,
        reranker=cfg.reranker,
        self_querying=SelfQuerying(fabrica.trabalhador()) if cfg.self_querying else None,
        minimo_candidatos=cfg.minimo_candidatos_filtrados,
    )


def montar_store(cfg: Config, pool: ConnectionPool) -> PostgresStore:
    """A Memória Semântica usa sempre o MiniLM (384 dimensões), qualquer que seja o embedder
    do RAG, para a memória não depender de qual coleção está no ar."""
    embedder = criar_embedder("minilm", cfg)
    return criar_store_postgres(pool, embedder.embed, dims=embedder.dims)


class Sistema:
    """As peças que o grafo usa, montadas uma vez por processo."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.fabrica = FabricaDeModelos(cfg)
        self.retriever = montar_retriever(cfg, self.fabrica)
        self.observabilidade = Observabilidade(cfg)

    def juiz(self) -> BaseChatModel:
        return self.fabrica.juiz()

    def gerador(self) -> BaseChatModel:
        return self.fabrica.gerador()

    def construir_grafo(
        self,
        *,
        pedidos: StoreDePedidos,
        tickets: StoreDeTickets,
        checkpointer: BaseCheckpointSaver,
        store: BaseStore,
    ) -> CompiledStateGraph:
        deps = Dependencias(
            config=self.cfg,
            fabrica=self.fabrica,
            retriever=self.retriever,
            pedidos=pedidos,
            tickets=tickets,
            observabilidade=self.observabilidade,
        )
        return construir_grafo(deps, checkpointer=checkpointer, store=store)


def montar_executor(cfg: Config) -> ExecutorPorTipo:
    """O executor do worker: o grafo de produção para os jobs do chat (stores, checkpointer
    e Store do LangGraph no mesmo pool) e a amostra ao vivo para os jobs de eval."""
    pool = criar_pool(cfg.database_url)
    sistema = Sistema(cfg)
    grafo = sistema.construir_grafo(
        pedidos=StoreDePedidosPostgres(pool),
        tickets=StoreDeTicketsPostgres(pool),
        checkpointer=PostgresSaver(pool),
        store=montar_store(cfg, pool),
    )
    do_grafo = ExecutorDoGrafo(
        grafo,
        observabilidade=sistema.observabilidade,
        tokens_antes_do_guardrail=cfg.tokens_antes_do_guardrail,
    )
    avaliacao = ExecutorDeAvaliacao(cfg, sistema, RegistroPostgres(pool))
    return ExecutorPorTipo({"mensagem": do_grafo, "retomada": do_grafo, "eval": avaliacao})


def montar_api(cfg: Config) -> FastAPI:
    pool = criar_pool(cfg.database_url)
    memoria = MemoriaProcedural(montar_store(cfg, pool))
    return criar_app(cfg, pool=pool, memoria_procedural=memoria)
