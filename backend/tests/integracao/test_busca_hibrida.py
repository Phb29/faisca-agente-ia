"""Busca híbrida contra um Qdrant real, com uma coleção pequena ingerida no próprio teste.

Roda só com `QDRANT_URL` no ambiente. ColBERT e BM25 baixam os modelos do HuggingFace
na primeira execução (cache em ~/.cache).
"""

import os
import uuid
from datetime import date
from pathlib import Path

import pytest
from qdrant_client import QdrantClient

from ampere.nucleo.falsos import ModeloFalso
from ampere.rag.busca import RetrieverFalso, RetrieverQdrant
from ampere.rag.chunkers import Chunk, ChunkerMarkdown
from ampere.rag.documentos import carregar_documentos
from ampere.rag.embedders import EmbedderFalso
from ampere.rag.filtro import FiltroDeBusca
from ampere.rag.indice import criar_colecao, indexar_chunks
from ampere.rag.self_querying import SelfQuerying

DOCUMENTOS = {
    "garantia_notebooks.md": (
        "garantia",
        "notebooks",
        "# Garantia de notebooks\n\nA garantia do notebook é de 12 meses e cobre defeitos "
        "de fabricação da placa e da tela.\n\n## Como acionar\n\nAbra um chamado com o "
        "número do Pedido e o número de série do notebook.",
    ),
    "garantia_celulares.md": (
        "garantia",
        "celulares",
        "# Garantia de celulares\n\nA garantia do celular é de 12 meses e cobre defeitos "
        "de fabricação da bateria e da câmera.\n\n## Como acionar\n\nAbra um chamado com "
        "o número do Pedido e o IMEI do celular.",
    ),
    "frete_todos.md": (
        "frete",
        "todos",
        "# Frete\n\nO frete é grátis para compras acima de 300 reais em todo o Brasil.\n\n"
        "## Prazo\n\nO prazo de entrega é de 3 a 10 dias úteis.",
    ),
    "troca_acessorios.md": (
        "troca",
        "acessorios",
        "# Troca de acessórios\n\nFones, capas e carregadores podem ser trocados em até "
        "7 dias após o recebimento.\n\n## Como trocar\n\nLeve o acessório lacrado a uma loja.",
    ),
}


def escrever_documentos(pasta: Path) -> None:
    for nome, (categoria, produto, texto) in DOCUMENTOS.items():
        pasta.joinpath(nome).write_text(
            f"---\ncategoria: {categoria}\nproduto: {produto}\nvigencia: 2026-01-01\n"
            f"tipo: politica\n---\n{texto}\n",
            encoding="utf-8",
        )


@pytest.fixture(scope="module")
def client() -> QdrantClient:
    url = os.environ.get("QDRANT_URL")
    if not url:
        pytest.skip("QDRANT_URL não definido")
    return QdrantClient(url=url)


@pytest.fixture(scope="module")
def colecao(client: QdrantClient, tmp_path_factory, request) -> str:
    pasta = tmp_path_factory.mktemp("base")
    escrever_documentos(pasta)
    nome = f"politicas__teste__{uuid.uuid4().hex}"
    request.addfinalizer(lambda: client.delete_collection(nome))
    embedder = EmbedderFalso()
    criar_colecao(client, nome, embedder.dims, recriar=True)
    chunks = [c for d in carregar_documentos(pasta) for c in ChunkerMarkdown().dividir(d)]
    total = indexar_chunks(client, nome, chunks, embedder, com_colbert=True)
    assert total == len(chunks) == 8
    return nome


@pytest.mark.integracao
def test_filtro_por_produto_traz_celulares_e_exclui_notebooks(client, colecao):
    retriever = RetrieverQdrant(client, colecao, EmbedderFalso(), reranker="nenhum")

    chunks = retriever.buscar(
        "garantia do meu celular", k=5, filtro=FiltroDeBusca(produto="celulares")
    )

    assert chunks
    assert chunks[0].documento == "garantia_celulares.md"
    documentos = {c.documento for c in chunks}
    assert "garantia_notebooks.md" not in documentos
    assert "troca_acessorios.md" not in documentos
    assert documentos <= {"garantia_celulares.md", "frete_todos.md"}


@pytest.mark.integracao
def test_busca_com_colbert_devolve_ate_k_chunks_com_score(client, colecao):
    retriever = RetrieverQdrant(client, colecao, EmbedderFalso(), reranker="colbert")

    chunks = retriever.buscar("qual o prazo de entrega do frete", k=3)

    assert 0 < len(chunks) <= 3
    assert all(isinstance(c, Chunk) for c in chunks)
    assert all(isinstance(c.score, float) for c in chunks)
    assert "frete_todos.md" in {c.documento for c in chunks}


@pytest.mark.integracao
def test_self_querying_com_filtro_sem_resultado_cai_para_busca_sem_filtro(client, colecao):
    trabalhador = ModeloFalso([FiltroDeBusca(categoria="cadastro")])
    retriever = RetrieverQdrant(
        client,
        colecao,
        EmbedderFalso(),
        reranker="nenhum",
        self_querying=SelfQuerying(trabalhador),
        minimo_candidatos=1,
    )

    chunks = retriever.buscar("garantia", k=3)

    assert chunks
    assert retriever.ultimo_filtro is None
    assert len(trabalhador.chamadas) == 1


@pytest.mark.integracao
def test_self_querying_com_filtro_que_bate_e_aplicado(client, colecao):
    trabalhador = ModeloFalso([FiltroDeBusca(categoria="troca")])
    retriever = RetrieverQdrant(
        client,
        colecao,
        EmbedderFalso(),
        reranker="nenhum",
        self_querying=SelfQuerying(trabalhador),
        minimo_candidatos=1,
    )

    chunks = retriever.buscar("como troco meu fone", k=5)

    assert {c.documento for c in chunks} == {"troca_acessorios.md"}
    assert retriever.ultimo_filtro == FiltroDeBusca(categoria="troca")


@pytest.mark.integracao
def test_vigencia_minima_usa_o_indice_datetime(client, colecao):
    retriever = RetrieverQdrant(
        client, colecao, EmbedderFalso(), reranker="nenhum", minimo_candidatos=1
    )

    vigentes = retriever.buscar(
        "frete", k=8, filtro=FiltroDeBusca(vigencia_minima=date(2026, 1, 1))
    )
    assert len(vigentes) == 8
    assert retriever.ultimo_filtro is not None

    futuras = retriever.buscar("frete", k=8, filtro=FiltroDeBusca(vigencia_minima=date(2027, 1, 1)))
    assert retriever.ultimo_filtro is None, "nada vige em 2027, então caiu para busca sem filtro"
    assert len(futuras) == 8


def test_retriever_falso_devolve_lista_fixa_e_guarda_perguntas():
    chunk = Chunk(
        texto="x",
        documento="d.md",
        categoria="frete",
        produto="todos",
        vigencia="2026-01-01",
        tipo="politica",
        indice=0,
    )
    retriever = RetrieverFalso([chunk])

    assert retriever.buscar("frete?", k=1) == [chunk]
    assert retriever.perguntas == ["frete?"]
