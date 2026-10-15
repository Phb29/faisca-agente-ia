"""Comandos de operação (`ampere`) e dos evals (`ampere-evals`).

Cada comando importa só o que usa, para `ampere --help` e `ampere migrate` não carregarem
modelos de embedding à toa. A montagem do sistema fica em `ampere/composicao.py`.
"""

import logging

import typer

from ampere.nucleo.config import config

app = typer.Typer(help="Suporte Ampère: comandos de operação.", no_args_is_help=True)
evals = typer.Typer(
    help="Suporte Ampère: evals com modelos reais (fora do pytest).", no_args_is_help=True
)
app.add_typer(evals, name="evals")


def _configurar_logs() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@app.command()
def migrate() -> None:
    """Cria as tabelas da fila, das Conversas e do LangGraph (checkpointer e Store)."""
    from ampere.nucleo.migracao import migrar

    aplicadas = migrar(config().database_url)
    typer.echo(f"migrações aplicadas: {', '.join(aplicadas) or 'nenhuma nova'}")


@app.command()
def seed() -> None:
    """Popula Clientes, Pedidos e um Reembolso recente (dados fictícios da Loja)."""
    from ampere.loja.seed import semear
    from ampere.nucleo.banco import conectar

    with conectar(config().database_url) as conn:
        inseridos = semear(conn)
    typer.echo(f"seed: {inseridos}")


@app.command()
def ingest(
    embedder: str = typer.Option(None, help="minilm | openai (padrão: EMBEDDER do .env)"),
    chunker: str = typer.Option(None, help="recursivo | markdown | semantico"),
    todas: bool = typer.Option(False, "--todas", help="Ingere as seis combinações."),
    sem_colbert: bool = typer.Option(False, "--sem-colbert", help="Não gera o vetor ColBERT."),
) -> None:
    """Ingere a Base de Conhecimento no Qdrant, numa coleção por (embedder, chunker)."""
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
    """Sobe a API HTTP (FastAPI)."""
    import uvicorn

    from ampere.composicao import montar_api

    _configurar_logs()
    uvicorn.run(montar_api(config()), host=host, port=port)


@app.command()
def worker(uma_vez: bool = typer.Option(False, "--uma-vez", help="Esvazia a fila e sai.")) -> None:
    """Consome a fila, executa o grafo e publica os eventos por NOTIFY."""
    from ampere.composicao import montar_executor
    from ampere.fila.worker import rodar_worker

    _configurar_logs()
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
    """Um turno do grafo real por cenário: intenção, Ação e desfecho por código, e o juiz."""
    from ampere.composicao import Sistema
    from ampere.evals.agente import rodar

    cfg = config()
    rodar(cfg, Sistema(cfg), amostra=amostra)


@evals.command("calibracao")
def evals_calibracao(
    seed: int = typer.Option(0, "--seed", help="Seed da divisão treino/dev/teste."),
) -> None:
    """Juiz contra rótulos humanos: TPR, TNR, matriz, desacordos e Rogan-Gladen com IC."""
    from ampere.evals.calibracao import rodar

    rodar(config(), seed=seed)


if __name__ == "__main__":
    app()
