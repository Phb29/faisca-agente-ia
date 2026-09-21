"""CLI operacional: migrate, seed, ingest, api e worker.

Este arquivo é a raiz de composição do sistema: o único lugar que liga config, modelos,
retriever, stores, grafo, executor, worker e API. Fica fora das pastas de conceito de
propósito, para nenhuma delas precisar importar do grafo (ver docs/adr/0005).
"""

import typer

from ampere.nucleo.config import Config, config

app = typer.Typer(help="Suporte Ampère: comandos de operação.", no_args_is_help=True)
evals = typer.Typer(
    help="Suporte Ampère: evals com modelos reais (fora do pytest).", no_args_is_help=True
)
app.add_typer(evals, name="evals")


@app.command()
def migrate() -> None:
    """Cria as tabelas da fila, das Conversas e do LangGraph (checkpointer e store)."""
    from ampere.fila.tabelas import migrar

    aplicadas = migrar(config().database_url)
    typer.echo(f"migrações aplicadas: {aplicadas or 'nenhuma nova'}")


@app.command()
def seed() -> None:
    """Popula Clientes, Pedidos e um Reembolso recente (dados fictícios)."""
    from ampere.fila.seed import semear
    from ampere.nucleo.banco import conectar

    with conectar(config().database_url) as conn:
        contagem = semear(conn)
    typer.echo(f"seed: {contagem}")


@app.command()
def ingest(
    embedder: str = typer.Option(None, help="minilm | openai (padrão: EMBEDDER do .env)"),
    chunker: str = typer.Option(None, help="recursivo | markdown | semantico"),
    todas: bool = typer.Option(False, "--todas", help="Ingere as seis combinações."),
    sem_colbert: bool = typer.Option(False, "--sem-colbert", help="Não gera o vetor ColBERT."),
) -> None:
    """Ingere a Base de Conhecimento no Qdrant numa coleção por (embedder, chunker)."""
    from qdrant_client import QdrantClient

    from ampere.rag.chunkers import criar_chunker
    from ampere.rag.colecao import todas_as_combinacoes
    from ampere.rag.embedders import criar_embedder
    from ampere.rag.ingestao import PASTA_PADRAO, ingerir

    cfg = config()
    client = QdrantClient(url=cfg.qdrant_url)
    combinacoes = (
        todas_as_combinacoes() if todas else [(embedder or cfg.embedder, chunker or cfg.chunker)]
    )
    for nome_embedder, nome_chunker in combinacoes:
        emb = criar_embedder(nome_embedder, cfg)
        chk = criar_chunker(nome_chunker, embed=emb.embed)
        total = ingerir(PASTA_PADRAO, client, emb, chk, com_colbert=not sem_colbert)
        typer.echo(f"{nome_embedder} + {nome_chunker}: {total} chunks")


@app.command()
def api(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Sobe a API HTTP (FastAPI) com a Memória Procedural ligada ao Store do LangGraph."""
    import uvicorn

    uvicorn.run(montar_api(config()), host=host, port=port)


@app.command()
def worker(uma_vez: bool = typer.Option(False, "--uma-vez")) -> None:
    """Consome a fila e executa o grafo, publicando os eventos por NOTIFY."""
    from ampere.fila.worker import rodar_worker

    cfg = config()
    rodar_worker(cfg.database_url, montar_executor(cfg), uma_vez=uma_vez)


@evals.command("rag")
def evals_rag(
    so_retrieval: bool = typer.Option(
        False, "--so-retrieval", help="Só Recall@5 e MRR, sem gerador nem juiz."
    ),
    amostra: int = typer.Option(None, "--amostra", help="Usa só as N primeiras perguntas."),
) -> None:
    """Recall@5 e MRR por variante (embedder, chunker, reranker, self-querying) e juiz."""
    from ampere.evals.rag import rodar

    rodar(config(), so_retrieval=so_retrieval, amostra=amostra)


@evals.command("agente")
def evals_agente(
    amostra: int = typer.Option(None, "--amostra", help="Usa só os N primeiros cenários."),
) -> None:
    """Um turno do grafo real por cenário: intenção, Ação e desfecho por código, mais o juiz."""
    from ampere.evals.agente import rodar

    cfg = config()
    rodar(cfg, ComposicaoDosEvals(cfg), amostra=amostra)


@evals.command("calibracao")
def evals_calibracao(
    seed: int = typer.Option(0, "--seed", help="Seed da divisão treino/dev/teste."),
) -> None:
    """Juiz contra rótulos humanos: TPR, TNR, matriz, desacordos e Rogan-Gladen com IC."""
    from ampere.evals.calibracao import rodar

    rodar(config(), seed=seed)


class ComposicaoDosEvals:
    """Entrega ao eval do agente o grafo real (modelos, Jev e retriever de produção)."""

    def __init__(self, cfg: Config) -> None:
        from ampere.observabilidade.langfuse import Observabilidade

        self.cfg = cfg
        self.fabrica = montar_fabrica(cfg)
        self.retriever = montar_retriever(cfg, self.fabrica)
        self.observabilidade = Observabilidade(cfg)

    def construir_grafo(self, *, pedidos, tickets, checkpointer, store):
        from ampere.grafo.construtor import Dependencias, construir_grafo

        deps = Dependencias(
            config=self.cfg,
            fabrica=self.fabrica,
            retriever=self.retriever,
            pedidos=pedidos,
            tickets=tickets,
            observabilidade=self.observabilidade,
        )
        return construir_grafo(deps, checkpointer=checkpointer, store=store)


def montar_fabrica(cfg: Config):
    from ampere.nucleo.modelos import FabricaDeModelos

    return FabricaDeModelos(cfg)


def montar_retriever(cfg: Config, fabrica):
    from qdrant_client import QdrantClient

    from ampere.rag.busca import RetrieverQdrant
    from ampere.rag.colecao import nome_da_colecao
    from ampere.rag.embedders import criar_embedder
    from ampere.rag.self_querying import SelfQuerying

    embedder = criar_embedder(cfg.embedder, cfg)
    return RetrieverQdrant(
        QdrantClient(url=cfg.qdrant_url),
        nome_da_colecao(embedder.nome, cfg.chunker),
        embedder,
        reranker=cfg.reranker,
        self_querying=SelfQuerying(fabrica.trabalhador()) if cfg.self_querying else None,
        minimo_candidatos=cfg.minimo_candidatos_filtrados,
    )


def montar_store(cfg: Config):
    from ampere.memoria.store import criar_store_postgres
    from ampere.rag.embedders import criar_embedder

    embedder = criar_embedder("minilm", cfg)
    return criar_store_postgres(cfg.database_url, embedder.embed, dims=embedder.dims)


def montar_grafo(cfg: Config, conn):
    from langgraph.checkpoint.postgres import PostgresSaver

    from ampere.acoes.pedidos import StoreDePedidosPostgres
    from ampere.acoes.ticket import StoreDeTicketsPostgres
    from ampere.grafo.construtor import Dependencias, construir_grafo
    from ampere.nucleo.banco import conectar
    from ampere.observabilidade.langfuse import Observabilidade

    fabrica = montar_fabrica(cfg)
    deps = Dependencias(
        config=cfg,
        fabrica=fabrica,
        retriever=montar_retriever(cfg, fabrica),
        pedidos=StoreDePedidosPostgres(conn),
        tickets=StoreDeTicketsPostgres(conn),
        observabilidade=Observabilidade(cfg),
    )
    checkpointer = PostgresSaver(conectar(cfg.database_url, autocommit=True))
    return construir_grafo(deps, checkpointer=checkpointer, store=montar_store(cfg)), deps


def montar_executor(cfg: Config):
    from ampere.fila.executor import ExecutorDoGrafo
    from ampere.nucleo.banco import conectar

    conn = conectar(cfg.database_url, autocommit=True)
    grafo, deps = montar_grafo(cfg, conn)
    return ExecutorDoGrafo(grafo, observabilidade=deps.observabilidade)


def montar_api(cfg: Config):
    from ampere.api.app import criar_app
    from ampere.memoria.carregar import ler_procedural
    from ampere.memoria.salvar import escrever_procedural

    store = montar_store(cfg)

    class MemoriaProceduralNoStore:
        def ler(self, cliente_id: str) -> str:
            return ler_procedural(store, cliente_id)

        def escrever(self, cliente_id: str, texto: str) -> None:
            escrever_procedural(store, cliente_id, texto)

    return criar_app(cfg, memoria_procedural=MemoriaProceduralNoStore())


if __name__ == "__main__":
    app()
