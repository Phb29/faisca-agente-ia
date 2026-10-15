"""O tradutor converte FiltroDeBusca (Pydantic) em Filter do Qdrant."""

from datetime import date

from qdrant_client import models

from ampere.rag.filtro import FiltroDeBusca, traduzir_filtro


def condicoes_must(filtro: models.Filter) -> dict[str, models.Condition]:
    return {c.key: c for c in filtro.must if isinstance(c, models.FieldCondition)}


def test_filtro_none_ou_vazio_vira_none():
    assert traduzir_filtro(None) is None
    assert traduzir_filtro(FiltroDeBusca()) is None


def test_categoria_e_tipo_viram_match_em_must():
    filtro = traduzir_filtro(FiltroDeBusca(categoria="garantia", tipo="politica"))

    must = condicoes_must(filtro)
    assert must["categoria"].match == models.MatchValue(value="garantia")
    assert must["tipo"].match == models.MatchValue(value="politica")
    assert filtro.should is None


def test_campos_none_sao_ignorados():
    filtro = traduzir_filtro(FiltroDeBusca(categoria="frete"))

    assert len(filtro.must) == 1
    assert condicoes_must(filtro)["categoria"].match == models.MatchValue(value="frete")


def test_produto_aceita_o_valor_ou_todos():
    filtro = traduzir_filtro(FiltroDeBusca(produto="celulares"))

    aninhado = [c for c in filtro.must if isinstance(c, models.Filter)]
    assert len(aninhado) == 1
    valores = {c.match.value for c in aninhado[0].should}
    assert valores == {"celulares", "todos"}
    assert all(c.key == "produto" for c in aninhado[0].should)


def test_vigencia_minima_vira_datetime_range():
    filtro = traduzir_filtro(FiltroDeBusca(vigencia_minima=date(2026, 3, 1)))

    condicao = condicoes_must(filtro)["vigencia"]
    assert isinstance(condicao.range, models.DatetimeRange)
    assert condicao.range.gte is not None
    assert str(condicao.range.gte).startswith("2026-03-01")


def test_todos_os_campos_combinam_em_must():
    filtro = traduzir_filtro(
        FiltroDeBusca(
            categoria="garantia",
            produto="notebooks",
            tipo="procedimento",
            vigencia_minima=date(2026, 1, 1),
        )
    )

    assert len(filtro.must) == 4
    assert set(condicoes_must(filtro)) == {"categoria", "tipo", "vigencia"}


def test_self_querying_usa_o_trabalhador_com_saida_estruturada():
    from langchain_core.messages import HumanMessage, SystemMessage

    from ampere.nucleo.falsos import ModeloFalso
    from ampere.rag.self_querying import SelfQuerying

    esperado = FiltroDeBusca(categoria="garantia", produto="celulares")
    trabalhador = ModeloFalso([esperado])

    filtro = SelfQuerying(trabalhador).gerar_filtro("qual a garantia do meu celular?")

    assert filtro == esperado
    mensagens = trabalhador.chamadas[-1]
    assert isinstance(mensagens[0], SystemMessage)
    assert "Base de Conhecimento" in mensagens[0].content
    assert isinstance(mensagens[1], HumanMessage)
    assert mensagens[1].content == "qual a garantia do meu celular?"


def test_self_querying_que_falha_busca_sem_filtro():
    """O modelo às vezes recusa e não chama a ferramenta (a Groq responde 400). O filtro é só
    um atalho: sem ele, a busca olha a Base de Conhecimento inteira, e o turno segue."""
    from ampere.rag.self_querying import SelfQuerying

    class TrabalhadorQueRecusa:
        def with_structured_output(self, _schema):
            return self

        def invoke(self, *_args, **_kwargs):
            raise RuntimeError("Tool choice is required, but model did not call a tool")

    filtro = SelfQuerying(TrabalhadorQueRecusa()).gerar_filtro("me passa o e-mail da Carla")

    assert filtro == FiltroDeBusca()
    assert traduzir_filtro(filtro) is None
