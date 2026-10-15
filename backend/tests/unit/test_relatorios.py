"""Relatórios dos evals (o que vira uma Execução) e os casos da amostra ao vivo."""

import random

import pytest

from ampere.evals import rag
from ampere.evals.juiz import Veredito
from ampere.evals.relatorio import Sorteado, caso_com_erro, consumir, contexto_base, media
from ampere.nucleo.config import Config
from ampere.nucleo.falsos import ModeloFalso
from ampere.rag.busca import RetrieverFalso
from ampere.rag.chunkers import Chunk


def chunk(documento: str, texto: str = "trecho") -> Chunk:
    return Chunk(
        texto=texto,
        documento=documento,
        categoria="troca",
        produto="notebooks",
        vigencia="2026-01-01",
        tipo="politica",
        indice=0,
    )


def rodar_passos(passos):
    """Roda os passos de um caso e devolve (fases soltas, resultado)."""
    fases = []
    while True:
        try:
            fases.append(next(passos))
        except StopIteration as fim:
            return fases, fim.value


# --- base comum -------------------------------------------------------------------------------


def test_consumir_ignora_as_fases_e_devolve_o_resultado():
    def passos():
        yield "busca"
        yield "juiz"
        return {"id": "x"}

    assert consumir(passos()) == {"id": "x"}


def test_caso_com_erro_tem_so_os_campos_comuns():
    sorteado = Sorteado(id="ag06", texto="Onde está meu pedido?", grupo="transacao", item=None)

    assert caso_com_erro(sorteado, "cota estourada", 1.234) == {
        "id": "ag06",
        "texto": "Onde está meu pedido?",
        "grupo": "transacao",
        "duracao_s": 1.23,
        "erro": "cota estourada",
    }
    assert sorteado.cartao() == {
        "id": "ag06",
        "texto": "Onde está meu pedido?",
        "grupo": "transacao",
    }


def test_contexto_base_registra_modo_modelos_prompts_e_tamanho():
    config = Config(modelos_falsos=True)

    contexto = contexto_base(config, prompts=["juiz_resolucao"], n=31)

    assert contexto["modelos_falsos"] is True
    assert contexto["gerador"] == config.modelo_gerador
    assert contexto["juiz"] == config.modelo_juiz
    assert contexto["trabalhador"] == config.modelo_trabalhador
    assert set(contexto["prompts"]) == {"juiz_resolucao"}
    assert contexto["n"] == 31


def test_media_de_nada_e_nula():
    assert media([]) is None
    assert media([1.0, 0.0]) == pytest.approx(0.5)


# --- busca (RAG) ------------------------------------------------------------------------------


def linha_rag(pergunta="Quantos dias para trocar?", esperado="troca.md", origem="manual"):
    return rag.LinhaRag(
        pergunta=pergunta, documento_esperado=esperado, resposta_referencia="7 dias", origem=origem
    )


def test_caso_rag_marca_a_posicao_do_documento_certo_e_os_vereditos():
    retrieval = rag.RetrievalDaPergunta(
        pergunta="p",
        documento_esperado="troca.md",
        recuperados=["frete.md", "troca.md"],
        recall=1.0,
        rr=0.5,
        filtro={"categoria": "troca"},
        duracao_s=0.4,
    )
    geracao = rag.VereditoDaGeracao(
        pergunta="p",
        resposta="7 dias",
        fidelidade=Veredito(aprovada=True, critica="fiel"),
        relevancia=Veredito(aprovada=False, critica="fugiu"),
        duracao_s=1.0,
    )

    caso = rag.caso_rag("rag-003", linha_rag(pergunta="p"), retrieval, geracao)

    assert caso["id"] == "rag-003"
    assert caso["texto"] == "p"
    assert caso["grupo"] == "manual"
    assert caso["posicao"] == 2
    assert caso["recuperados"] == ["frete.md", "troca.md"]
    assert caso["filtro"] == {"categoria": "troca"}
    assert caso["resposta"] == "7 dias"
    assert caso["fidelidade"] == {"aprovada": True, "critica": "fiel"}
    assert caso["relevancia"] == {"aprovada": False, "critica": "fugiu"}
    assert caso["duracao_s"] == pytest.approx(1.4)
    assert caso["erro"] is None


def test_caso_rag_fora_do_top5_e_sem_geracao():
    retrieval = rag.RetrievalDaPergunta(
        pergunta="p",
        documento_esperado="troca.md",
        recuperados=["a.md", "b.md", "c.md", "d.md", "e.md"],
        recall=0.0,
        rr=0.0,
    )

    caso = rag.caso_rag("rag-000", linha_rag(pergunta="p"), retrieval, None)

    assert caso["posicao"] is None
    assert caso["resposta"] is None
    assert caso["fidelidade"] is None
    assert caso["filtro"] is None


def test_resumo_rag_conta_so_os_casos_sem_erro():
    casos = [
        {"posicao": 1, "fidelidade": {"aprovada": True}, "relevancia": {"aprovada": True}},
        {"posicao": 2, "fidelidade": {"aprovada": False}, "relevancia": {"aprovada": True}},
        {"posicao": None, "fidelidade": None, "relevancia": None},
        {"id": "rag-009", "erro": "cota da Groq"},
    ]
    variantes = [{"nome": "minilm+markdown+colbert+sq", "recall_at_5": 0.9, "mrr": 0.8}]

    resumo = rag.resumo_rag("minilm+markdown+colbert+sq", casos, variantes)

    assert resumo["n"] == 3
    assert resumo["recall_at_5"] == pytest.approx(2 / 3)
    assert resumo["mrr"] == pytest.approx((1 + 0.5 + 0) / 3)
    assert resumo["fidelidade"] == pytest.approx(0.5)
    assert resumo["relevancia"] == pytest.approx(1.0)
    assert resumo["variante_no_ar"] == "minilm+markdown+colbert+sq"
    assert resumo["variantes"] == variantes


def test_sortear_amostra_rag_comeca_por_uma_adversarial_e_usa_o_id_da_posicao():
    golden = [
        linha_rag(pergunta=f"p{i}", origem="adversarial" if i in (3, 7) else "manual")
        for i in range(10)
    ]

    for seed in range(5):
        sorteados = rag.sortear_amostra(random.Random(seed), golden)

        assert len({s.id for s in sorteados}) == 3
        assert sorteados[0].grupo == "adversarial"
        for sorteado in sorteados:
            assert sorteado.id == rag.id_da_pergunta(golden.index(sorteado.item))
            assert sorteado.texto == sorteado.item.pergunta
            assert sorteado.grupo == sorteado.item.origem


def test_sortear_amostra_rag_funciona_com_o_golden_real():
    sorteados = rag.sortear_amostra(random.Random(1))

    assert len(sorteados) == 3
    assert sorteados[0].grupo == "adversarial"


def test_caso_ao_vivo_rag_solta_busca_resposta_e_juiz():
    sorteado = Sorteado(
        id="rag-001", texto="p", grupo="manual", item=linha_rag(pergunta="p", esperado="troca.md")
    )
    juiz = ModeloFalso(
        [Veredito(aprovada=True, critica="fiel"), Veredito(aprovada=True, critica="relevante")]
    )

    fases, caso = rodar_passos(
        rag.caso_ao_vivo(
            sorteado,
            retriever=RetrieverFalso([chunk("troca.md")]),
            gerador=ModeloFalso(["Você tem 7 dias."]),
            juiz=juiz,
        )
    )

    assert fases == ["busca", "resposta", "juiz"]
    assert caso["posicao"] == 1
    assert caso["resposta"] == "Você tem 7 dias."
    assert caso["fidelidade"]["critica"] == "fiel"
    assert caso["relevancia"]["critica"] == "relevante"
