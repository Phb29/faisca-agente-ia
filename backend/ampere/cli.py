"""Comandos de operação (`ampere`) e dos evals (`ampere-evals`).

Cada comando importa só o que usa, para `ampere --help` e `ampere migrate` não carregarem
modelos de embedding à toa. A montagem do sistema fica em `ampere/composicao.py`.
"""

import logging
import sys

import typer

from ampere.nucleo.config import config

app = typer.Typer(help="Suporte Faísca: comandos de operação.", no_args_is_help=True)
evals = typer.Typer(
    help="Suporte Faísca: evals com modelos reais (fora do pytest).", no_args_is_help=True
)
app.add_typer(evals, name="evals")


def _configurar_logs() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _salvar(eval: str, relatorio, *, sem_salvar: bool) -> None:
    """Grava a execução completa no banco do `.env`, para a Tela de Avaliação mostrar. Em
    produção, rode o eval de dentro do worker do Railway, que enxerga o banco e tem as
    chaves dos modelos: `railway ssh --service worker -- ampere-evals agente`."""
    if sem_salvar:
        return
    if relatorio is None:
        typer.echo("execução não gravada: a rodada não gerou relatório")
        return
    import psycopg

    from ampere.evals.execucoes import salvar_completa
    from ampere.nucleo.banco import conectar

    try:
        with conectar(config().database_url, autocommit=True) as conn:
            execucao_id = salvar_completa(
                conn,
                eval,
                contexto=relatorio.contexto,
                resumo=relatorio.resumo,
                casos=relatorio.casos,
            )
    except psycopg.Error as exc:
        typer.echo(f"execução não gravada: {exc}")
        return
    typer.echo(f"execução gravada: {execucao_id}")


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


@app.command("hash-senha")
def hash_senha() -> None:
    """Imprime o hash de uma senha para LOGIN_SENHA_HASH. No terminal, pede a senha duas
    vezes sem mostrar; fora dele, lê uma linha da entrada padrão."""
    import getpass
    import sys

    from ampere.acesso.senha import gerar_hash

    if sys.stdin.isatty():
        senha = getpass.getpass("Senha: ")
        if getpass.getpass("Repita a senha: ") != senha:
            typer.echo("as duas senhas não conferem", err=True)
            raise typer.Exit(1)
    else:
        senha = sys.stdin.readline().rstrip("\r\n")
    if not senha:
        typer.echo("senha vazia", err=True)
        raise typer.Exit(1)
    typer.echo(gerar_hash(senha))


# No Windows o uvicorn usa o ProactorEventLoop, que o psycopg assíncrono do SSE recusa.
LOOP_DA_API = "asyncio:SelectorEventLoop" if sys.platform == "win32" else "auto"


@app.command()
def api(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Sobe a API HTTP (FastAPI). Com `--host ::`, escuta IPv6 e IPv4 na mesma porta: a rede
    interna do Railway é IPv6, e o healthcheck pode chegar por IPv4."""
    import uvicorn

    from ampere.composicao import montar_api

    _configurar_logs()
    aplicacao = montar_api(config())
    if host != "::":
        uvicorn.run(aplicacao, host=host, port=port, loop=LOOP_DA_API)
        return
    servidor = uvicorn.Server(uvicorn.Config(aplicacao, host=host, port=port, loop=LOOP_DA_API))
    sock = _socket_ipv6_e_ipv4(port)
    logging.getLogger(__name__).info("api escutando em [::]:%d, IPv6 e IPv4", port)
    servidor.run(sockets=[sock])


def _socket_ipv6_e_ipv4(port: int):
    """Um socket em `::` que aceita IPv6 e IPv4 (este chega como `::ffff:a.b.c.d`). Quando o
    próprio uvicorn abre `::`, o asyncio liga o IPV6_V6ONLY, e o IPv4 fica de fora."""
    import socket

    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind(("::", port))
    return sock


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
    sem_salvar: bool = typer.Option(False, "--sem-salvar", help="Não grava a execução."),
) -> None:
    """Recall@5 e MRR por variante (embedder, chunker, reranker, self-querying) e juiz."""
    from ampere.evals.rag import rodar

    relatorio = rodar(config(), so_retrieval=so_retrieval, amostra=amostra)
    if amostra is not None:
        typer.echo("execução parcial (--amostra) não é gravada")
        return
    _salvar("rag", relatorio, sem_salvar=sem_salvar)


@evals.command("agente")
def evals_agente(
    amostra: int = typer.Option(None, "--amostra", help="Usa só os N primeiros cenários."),
    sem_salvar: bool = typer.Option(False, "--sem-salvar", help="Não grava a execução."),
) -> None:
    """Um turno do grafo real por cenário: intenção, Ação e desfecho por código, e o juiz."""
    from ampere.composicao import Sistema
    from ampere.evals.agente import rodar

    cfg = config()
    relatorio = rodar(cfg, Sistema(cfg), amostra=amostra)
    if amostra is not None:
        typer.echo("execução parcial (--amostra) não é gravada")
        return
    _salvar("agente", relatorio, sem_salvar=sem_salvar)


@evals.command("calibracao")
def evals_calibracao(
    seed: int = typer.Option(0, "--seed", help="Seed da divisão treino/dev/teste."),
    sem_salvar: bool = typer.Option(False, "--sem-salvar", help="Não grava a execução."),
) -> None:
    """Juiz contra rótulos humanos: TPR, TNR, matriz, desacordos e Rogan-Gladen com IC."""
    from ampere.evals.calibracao import rodar

    _salvar("juiz", rodar(config(), seed=seed), sem_salvar=sem_salvar)


if __name__ == "__main__":
    app()
