"""CLI dos evals: `ampere-evals rag|agente|calibracao`. Usa modelos reais; não roda no pytest."""

import typer

from ampere.nucleo.config import config

app = typer.Typer(help="Suporte Ampère: evals com modelos reais.", no_args_is_help=True)


@app.command()
def rag(
    so_retrieval: bool = typer.Option(
        False, "--so-retrieval", help="Só Recall@5 e MRR, sem gerador nem juiz."
    ),
    amostra: int = typer.Option(None, "--amostra", help="Usa só as N primeiras perguntas."),
) -> None:
    """Recall@5 e MRR por variante (embedder, chunker, reranker, self-querying) e juiz."""
    from ampere.evals.rag import rodar

    rodar(config(), so_retrieval=so_retrieval, amostra=amostra)


@app.command()
def agente(
    amostra: int = typer.Option(None, "--amostra", help="Usa só os N primeiros cenários."),
) -> None:
    """Um turno do grafo real por cenário: intenção, Ação e desfecho por código, mais o juiz."""
    from ampere.evals.agente import rodar

    rodar(config(), amostra=amostra)


@app.command()
def calibracao(
    seed: int = typer.Option(0, "--seed", help="Seed da divisão treino/dev/teste."),
) -> None:
    """Juiz contra rótulos humanos: TPR, TNR, matriz, desacordos e Rogan-Gladen com IC."""
    from ampere.evals.calibracao import rodar

    rodar(config(), seed=seed)


if __name__ == "__main__":
    app()
