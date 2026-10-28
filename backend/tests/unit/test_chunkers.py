"""Os três chunkers têm propriedades comuns: cobrem todo o texto, não geram chunk vazio,
numeram os índices em sequência e copiam os metadados do documento."""

import re
from collections import Counter

import pytest

from ampere.nucleo.falsos import embed_falso
from ampere.rag.chunkers import (
    Chunk,
    ChunkerMarkdown,
    ChunkerRecursivo,
    ChunkerSemantico,
    criar_chunker,
)
from ampere.rag.documentos import Documento, carregar_documentos

TEXTO = """Introdução sem cabeçalho, explicando o contexto da política de garantia.

# Garantia de notebooks

A garantia legal dos notebooks é de 90 dias. A garantia contratual da Faísca é de 12 meses.
Ela cobre defeitos de fabricação. Não cobre danos por mau uso, quedas ou líquidos.

## Como acionar

Abra um chamado pelo site informando o número do Pedido. Envie fotos do defeito.
A análise leva até 7 dias úteis. Se aprovada, o conserto leva até 30 dias.

### Prazos

Notebooks premium têm prazo de análise reduzido para 3 dias úteis.

## Exceções

Baterias têm garantia de 6 meses. Carregadores seguem a garantia do notebook.
"""


def documento(texto: str = TEXTO) -> Documento:
    return Documento(
        nome="garantia_notebooks.md",
        texto=texto,
        categoria="garantia",
        produto="notebooks",
        vigencia="2026-01-01",
        tipo="politica",
    )


def sem_brancos(texto: str) -> str:
    return re.sub(r"\s+", "", texto)


CHUNKERS = [
    pytest.param(ChunkerRecursivo(tamanho=120, sobreposicao=20), id="recursivo"),
    pytest.param(ChunkerMarkdown(), id="markdown"),
    pytest.param(ChunkerSemantico(embed=embed_falso), id="semantico"),
]


def palavras(texto: str) -> Counter:
    return Counter(re.findall(r"\w+", texto))


@pytest.mark.parametrize("chunker", CHUNKERS)
def test_chunks_cobrem_todas_as_palavras_do_documento(chunker):
    chunks = chunker.dividir(documento())

    nos_chunks = palavras(" ".join(c.texto for c in chunks))
    for palavra, quantidade in palavras(TEXTO).items():
        assert nos_chunks[palavra] >= quantidade, palavra


@pytest.mark.parametrize(
    "chunker",
    [
        pytest.param(ChunkerRecursivo(tamanho=120, sobreposicao=0), id="recursivo"),
        pytest.param(ChunkerMarkdown(), id="markdown"),
        pytest.param(ChunkerSemantico(embed=embed_falso), id="semantico"),
    ],
)
def test_sem_sobreposicao_a_concatenacao_e_o_texto_inteiro(chunker):
    chunks = chunker.dividir(documento())

    assert sem_brancos("".join(c.texto for c in chunks)) == sem_brancos(TEXTO)


@pytest.mark.parametrize("chunker", CHUNKERS)
def test_nenhum_chunk_vazio(chunker):
    chunks = chunker.dividir(documento())

    assert chunks
    assert all(c.texto.strip() for c in chunks)


@pytest.mark.parametrize("chunker", CHUNKERS)
def test_indices_sequenciais_e_metadados_copiados(chunker):
    doc = documento()

    chunks = chunker.dividir(doc)

    assert [c.indice for c in chunks] == list(range(len(chunks)))
    for c in chunks:
        assert isinstance(c, Chunk)
        assert c.documento == doc.nome
        assert c.categoria == doc.categoria
        assert c.produto == doc.produto
        assert c.vigencia == doc.vigencia
        assert c.tipo == doc.tipo
        assert c.score is None


def test_recursivo_respeita_o_tamanho():
    chunker = ChunkerRecursivo(tamanho=120, sobreposicao=20)

    chunks = chunker.dividir(documento())

    assert len(chunks) > 1
    assert all(len(c.texto) <= 120 for c in chunks)


def test_recursivo_texto_curto_vira_um_chunk_so():
    chunks = ChunkerRecursivo(tamanho=800, sobreposicao=100).dividir(documento("Texto curto."))

    assert [c.texto for c in chunks] == ["Texto curto."]


def test_markdown_um_chunk_por_secao_com_cabecalho_incluido():
    chunks = ChunkerMarkdown().dividir(documento())

    assert len(chunks) == 5
    assert chunks[0].texto.startswith("Introdução sem cabeçalho")
    assert chunks[1].texto.startswith("# Garantia de notebooks")
    assert chunks[2].texto.startswith("## Como acionar")
    assert chunks[3].texto.startswith("### Prazos")
    assert chunks[4].texto.startswith("## Exceções")


def test_markdown_sem_cabecalho_vira_um_chunk():
    chunks = ChunkerMarkdown().dividir(documento("Só um parágrafo.\n\nE outro."))

    assert len(chunks) == 1


def test_semantico_agrupa_frases_parecidas_mantendo_a_ordem():
    texto = (
        "A garantia cobre defeitos. O frete é grátis acima de 300 reais. "
        "A garantia não cobre quedas. O frete leva 5 dias."
    )

    chunks = ChunkerSemantico(embed=embed_falso, eps=0.9).dividir(documento(texto))

    assert chunks[0].texto.startswith("A garantia cobre defeitos.")
    for c in chunks:
        assert "garantia" in c.texto or "frete" in c.texto


def test_semantico_frases_isoladas_viram_chunk_proprio():
    texto = "Notebook azul. Pagamento com boleto vence em três dias. Cachorro late."

    chunks = ChunkerSemantico(embed=embed_falso, eps=0.1).dividir(documento(texto))

    assert len(chunks) == 3


def test_fabrica_de_chunkers():
    assert criar_chunker("recursivo").nome == "recursivo"
    assert criar_chunker("markdown").nome == "markdown"
    assert criar_chunker("semantico", embed=embed_falso).nome == "semantico"
    with pytest.raises(ValueError):
        criar_chunker("inexistente")
    with pytest.raises(ValueError):
        criar_chunker("semantico")


def test_carregar_documentos_le_frontmatter(tmp_path):
    (tmp_path / "frete_todos.md").write_text(
        "---\ncategoria: frete\nproduto: todos\nvigencia: 2026-01-01\ntipo: politica\n---\n"
        "# Frete\n\nGrátis acima de 300 reais.\n",
        encoding="utf-8",
    )
    (tmp_path / "ignorado.txt").write_text("nada", encoding="utf-8")

    docs = carregar_documentos(tmp_path)

    assert len(docs) == 1
    doc = docs[0]
    assert doc.nome == "frete_todos.md"
    assert doc.categoria == "frete"
    assert doc.produto == "todos"
    assert doc.vigencia == "2026-01-01"
    assert doc.tipo == "politica"
    assert doc.texto.startswith("# Frete")
