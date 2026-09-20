"""O nome da coleção é derivado do embedder e do chunker; há seis combinações."""

from ampere.rag.colecao import CHUNKERS, EMBEDDERS, nome_da_colecao, todas_as_combinacoes


def test_nome_da_colecao():
    assert nome_da_colecao("minilm", "markdown") == "politicas__minilm__markdown"
    assert nome_da_colecao("openai", "semantico") == "politicas__openai__semantico"


def test_todas_as_combinacoes_sao_seis():
    combinacoes = todas_as_combinacoes()

    assert len(combinacoes) == 6
    assert len(set(combinacoes)) == 6
    assert set(EMBEDDERS) == {"minilm", "openai"}
    assert set(CHUNKERS) == {"recursivo", "markdown", "semantico"}
    for embedder, chunker in combinacoes:
        assert embedder in EMBEDDERS
        assert chunker in CHUNKERS
        assert nome_da_colecao(embedder, chunker).startswith("politicas__")
