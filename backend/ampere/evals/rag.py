"""Eval do RAG: Recall@5 e MRR no nível do documento por variante, e o juiz sobre a geração.

Uma variante é (embedder, chunker, reranker, self-querying). Retrieval é barato e roda em
todas as coleções que existem no Qdrant; a geração usa o gerador e o juiz e por isso roda
só na variante configurada no .env.
"""

import csv
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from ampere.evals.juiz import Veredito, julgar_fidelidade, julgar_relevancia
from ampere.evals.metricas import mrr, recall_at_k
from ampere.grafo.prompts import carregar_prompt
from ampere.nucleo.config import Config
from ampere.rag.busca import Retriever, formatar_chunks
from ampere.rag.chunkers import Chunk

PASTA_DADOS = Path(__file__).parent / "dados"
NOME_DATASET = "golden_rag"


class LinhaRag(BaseModel):
    pergunta: str
    documento_esperado: str
    resposta_referencia: str
    origem: str


def carregar_golden_rag(caminho: Path = PASTA_DADOS / "golden_rag.csv") -> list[LinhaRag]:
    with Path(caminho).open(encoding="utf-8", newline="") as arquivo:
        return [LinhaRag.model_validate(linha) for linha in csv.DictReader(arquivo)]


# --- retrieval -----------------------------------------------------------------------------


def documentos_unicos(chunks: Sequence[Chunk]) -> list[str]:
    """Nomes de documento na ordem do ranking, sem repetição: a métrica é por documento."""
    vistos: list[str] = []
    for chunk in chunks:
        if chunk.documento not in vistos:
            vistos.append(chunk.documento)
    return vistos


@dataclass(frozen=True)
class RetrievalDaPergunta:
    pergunta: str
    documento_esperado: str
    recuperados: list[str]
    recall: float
    rr: float


@dataclass(frozen=True)
class ResultadoRetrieval:
    recall_at_5: float
    mrr: float
    n: int
    por_pergunta: list[RetrievalDaPergunta] = field(default_factory=list)


def avaliar_retrieval(
    retriever: Retriever, golden: Sequence[LinhaRag], *, k: int = 5
) -> ResultadoRetrieval:
    por_pergunta = []
    for linha in golden:
        recuperados = documentos_unicos(retriever.buscar(linha.pergunta, k=k))
        por_pergunta.append(
            RetrievalDaPergunta(
                pergunta=linha.pergunta,
                documento_esperado=linha.documento_esperado,
                recuperados=recuperados,
                recall=recall_at_k(recuperados, linha.documento_esperado, k=k),
                rr=mrr(recuperados, linha.documento_esperado),
            )
        )
    n = len(por_pergunta)
    return ResultadoRetrieval(
        recall_at_5=_media([r.recall for r in por_pergunta]),
        mrr=_media([r.rr for r in por_pergunta]),
        n=n,
        por_pergunta=por_pergunta,
    )


# --- geração -------------------------------------------------------------------------------


@dataclass(frozen=True)
class VereditoDaGeracao:
    pergunta: str
    resposta: str
    fidelidade: Veredito
    relevancia: Veredito


@dataclass(frozen=True)
class ResultadoGeracao:
    fidelidade: float
    relevancia: float
    n: int
    vereditos: list[VereditoDaGeracao] = field(default_factory=list)


def gerar_resposta(gerador: BaseChatModel, pergunta: str, chunks: Sequence[Chunk]) -> str:
    """Mesmo prompt `gerar_resposta` do grafo, sem memórias: mede só RAG + gerador."""
    prompt = carregar_prompt("gerar_resposta")
    sistema = prompt.renderizar(
        memoria_procedural="(nenhuma)",
        memorias="(nada registrado)",
        contexto=formatar_chunks(chunks),
        critica="",
    )
    resposta = gerador.invoke(
        [SystemMessage(sistema), HumanMessage(pergunta)], config={"metadata": prompt.metadata()}
    )
    return str(resposta.content)


def avaliar_geracao(
    gerador: BaseChatModel,
    juiz: BaseChatModel,
    retriever: Retriever,
    golden: Sequence[LinhaRag],
    *,
    amostra: int | None = None,
) -> ResultadoGeracao:
    vereditos = []
    for linha in list(golden)[:amostra]:
        chunks = retriever.buscar(linha.pergunta, k=5)
        resposta = gerar_resposta(gerador, linha.pergunta, chunks)
        vereditos.append(
            VereditoDaGeracao(
                pergunta=linha.pergunta,
                resposta=resposta,
                fidelidade=julgar_fidelidade(
                    juiz,
                    pergunta=linha.pergunta,
                    contexto=[c.texto for c in chunks],
                    resposta=resposta,
                ),
                relevancia=julgar_relevancia(juiz, pergunta=linha.pergunta, resposta=resposta),
            )
        )
    return ResultadoGeracao(
        fidelidade=_media([float(v.fidelidade.aprovada) for v in vereditos]),
        relevancia=_media([float(v.relevancia.aprovada) for v in vereditos]),
        n=len(vereditos),
        vereditos=vereditos,
    )


# --- variantes e execução -------------------------------------------------------------------


@dataclass(frozen=True)
class Variante:
    embedder: str
    chunker: str
    reranker: str
    self_querying: bool

    @property
    def nome(self) -> str:
        sq = "sq" if self.self_querying else "sem-sq"
        return f"{self.embedder}+{self.chunker}+{self.reranker}+{sq}"


def variantes_disponiveis(client: Any, config: Config) -> list[Variante]:
    """Toda combinação cuja coleção existe no Qdrant. `openai` exige chave da OpenAI e o
    self-querying exige o trabalhador (chave da Groq), a menos que os modelos sejam falsos."""
    from ampere.rag.colecao import nome_da_colecao, todas_as_combinacoes

    com_self_querying = (True, False) if tem_trabalhador(config) else (False,)
    variantes = []
    for embedder, chunker in todas_as_combinacoes():
        if embedder == "openai" and not config.openai_api_key:
            continue
        if not client.collection_exists(nome_da_colecao(embedder, chunker)):
            continue
        for reranker in ("colbert", "nenhum"):
            for self_querying in com_self_querying:
                variantes.append(Variante(embedder, chunker, reranker, self_querying))
    return variantes


def tem_trabalhador(config: Config) -> bool:
    return config.modelos_falsos or bool(config.groq_api_key)


def variante_configurada(config: Config) -> Variante:
    return Variante(config.embedder, config.chunker, config.reranker, config.self_querying)


def rodar(config: Config, *, so_retrieval: bool = False, amostra: int | None = None) -> list[dict]:
    from qdrant_client import QdrantClient
    from rich.console import Console
    from rich.table import Table

    from ampere.evals.datasets import cliente_langfuse
    from ampere.nucleo.modelos import FabricaDeModelos
    from ampere.rag.busca import RetrieverQdrant
    from ampere.rag.colecao import nome_da_colecao
    from ampere.rag.embedders import criar_embedder
    from ampere.rag.self_querying import SelfQuerying

    console = Console()
    golden = carregar_golden_rag()[:amostra]
    client = QdrantClient(url=config.qdrant_url)
    fabrica = FabricaDeModelos(config)
    variantes = variantes_disponiveis(client, config)
    if not variantes:
        console.print("[red]Nenhuma coleção encontrada no Qdrant. Rode `ampere ingest --todas`.")
        return []
    if not tem_trabalhador(config):
        console.print("[yellow]Sem GROQ_API_KEY: variantes com self-querying foram puladas.")
    configurada = variante_configurada(config)
    embedders: dict[str, Any] = {}
    linhas: list[dict] = []
    detalhes: dict[str, tuple[ResultadoRetrieval, ResultadoGeracao | None]] = {}

    for variante in variantes:
        if variante.embedder not in embedders:
            embedders[variante.embedder] = criar_embedder(variante.embedder, config)
        retriever = RetrieverQdrant(
            client,
            nome_da_colecao(variante.embedder, variante.chunker),
            embedders[variante.embedder],
            reranker=variante.reranker,  # type: ignore[arg-type]
            self_querying=SelfQuerying(fabrica.trabalhador()) if variante.self_querying else None,
            minimo_candidatos=config.minimo_candidatos_filtrados,
        )
        console.print(f"[dim]retrieval: {variante.nome}")
        retrieval = avaliar_retrieval(retriever, golden, k=5)
        geracao = None
        if not so_retrieval and variante == configurada:
            console.print(f"[dim]geração + juiz: {variante.nome} ({len(golden)} perguntas)")
            geracao = avaliar_geracao(fabrica.gerador(), fabrica.juiz(), retriever, golden)
        detalhes[variante.nome] = (retrieval, geracao)
        linhas.append(
            {
                "variante": variante.nome,
                "embedder": variante.embedder,
                "chunker": variante.chunker,
                "reranker": variante.reranker,
                "self_querying": variante.self_querying,
                "recall_at_5": retrieval.recall_at_5,
                "mrr": retrieval.mrr,
                "fidelidade": geracao.fidelidade if geracao else None,
                "relevancia": geracao.relevancia if geracao else None,
                "n": retrieval.n,
            }
        )

    tabela = Table(title=f"Eval do RAG ({len(golden)} perguntas)")
    for coluna in ("Embedder", "Chunker", "Reranker", "Self-querying", "Recall@5", "MRR"):
        tabela.add_column(
            coluna, justify="right" if coluna in ("Recall@5", "MRR") else "left", overflow="fold"
        )
    if not so_retrieval:
        tabela.add_column("Fidelidade", justify="right")
        tabela.add_column("Relevância", justify="right")
    for linha in linhas:
        celulas = [
            linha["embedder"],
            linha["chunker"],
            linha["reranker"],
            "sim" if linha["self_querying"] else "não",
            f"{linha['recall_at_5']:.2f}",
            f"{linha['mrr']:.2f}",
        ]
        if not so_retrieval:
            celulas += [_pct(linha["fidelidade"]), _pct(linha["relevancia"])]
        tabela.add_row(*celulas)
    console.print(tabela)
    for nome, (_, geracao) in detalhes.items():
        if geracao:
            _imprimir_vereditos(console, nome, geracao)

    cliente = cliente_langfuse(config)
    if cliente is not None:
        _publicar(cliente, golden, detalhes)
        console.print("[dim]Langfuse: dataset e runs publicados.")
    return linhas


def _imprimir_vereditos(console: Any, nome: str, geracao: ResultadoGeracao) -> None:
    from rich.table import Table

    tabela = Table(title=f"Geração: {nome}")
    for coluna in ("Pergunta", "Fidelidade", "Relevância", "Crítica"):
        tabela.add_column(coluna, overflow="fold")
    for v in geracao.vereditos:
        tabela.add_row(
            v.pergunta,
            _marca(v.fidelidade.aprovada),
            _marca(v.relevancia.aprovada),
            f"{v.fidelidade.critica} / {v.relevancia.critica}",
        )
    console.print(tabela)


def _publicar(
    cliente: Any,
    golden: Sequence[LinhaRag],
    detalhes: dict[str, tuple[ResultadoRetrieval, ResultadoGeracao | None]],
) -> None:
    from ampere.evals.datasets import publicar_dataset, publicar_run

    ids = {linha.pergunta: f"rag-{i:03d}" for i, linha in enumerate(golden)}
    publicar_dataset(
        cliente,
        NOME_DATASET,
        [
            {
                "id": ids[linha.pergunta],
                "input": {"id": ids[linha.pergunta], "pergunta": linha.pergunta},
                "expected_output": {
                    "documento_esperado": linha.documento_esperado,
                    "resposta_referencia": linha.resposta_referencia,
                },
                "metadata": {"origem": linha.origem},
            }
            for linha in golden
        ],
    )
    for nome, (retrieval, geracao) in detalhes.items():
        vereditos = {v.pergunta: v for v in geracao.vereditos} if geracao else {}
        resultados: dict[str, tuple[Any, dict]] = {}
        for r in retrieval.por_pergunta:
            scores: dict[str, tuple[Any, str | None]] = {
                "recall_at_5": (r.recall, None),
                "mrr": (r.rr, None),
            }
            saida: dict[str, Any] = {"recuperados": r.recuperados}
            if r.pergunta in vereditos:
                v = vereditos[r.pergunta]
                saida["resposta"] = v.resposta
                scores["fidelidade"] = (v.fidelidade.aprovada, v.fidelidade.critica)
                scores["relevancia"] = (v.relevancia.aprovada, v.relevancia.critica)
            resultados[ids[r.pergunta]] = (saida, scores)
        publicar_run(cliente, NOME_DATASET, nome, resultados, metadata={"variante": nome})


def _media(valores: Sequence[float]) -> float:
    return sum(valores) / len(valores) if valores else 0.0


def _pct(valor: float | None) -> str:
    return "—" if valor is None else f"{valor:.0%}"


def _marca(ok: bool) -> str:
    return "[green]✓[/green]" if ok else "[red]✗[/red]"
