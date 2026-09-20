"""Métricas dos evals: retrieval, classificação binária e correção de viés do juiz."""

import pytest

from ampere.evals.metricas import (
    MatrizDeConfusao,
    bootstrap_ic,
    matriz_de_confusao,
    mrr,
    recall_at_k,
    rogan_gladen,
    tnr,
    tpr,
)


def test_recall_at_k_no_nivel_do_documento():
    recuperados = ["frete_todos.md", "garantia_notebooks.md", "garantia_notebooks.md"]

    assert recall_at_k(recuperados, "garantia_notebooks.md", k=5) == 1.0
    assert recall_at_k(recuperados, "garantia_notebooks.md", k=1) == 0.0
    assert recall_at_k([], "x.md", k=5) == 0.0


def test_mrr_usa_a_posicao_do_primeiro_acerto():
    assert mrr(["a.md", "b.md", "b.md"], "b.md") == pytest.approx(0.5)
    assert mrr(["b.md", "a.md"], "b.md") == 1.0
    assert mrr(["a.md"], "b.md") == 0.0


def test_matriz_de_confusao_tpr_e_tnr():
    humano = [True, True, True, True, False, False, False, False]
    juiz = [True, True, True, False, False, False, True, True]

    matriz = matriz_de_confusao(humano, juiz)

    assert matriz == MatrizDeConfusao(vp=3, fn=1, vn=2, fp=2)
    assert tpr(matriz) == pytest.approx(0.75)
    assert tnr(matriz) == pytest.approx(0.5)


def test_tpr_e_tnr_sem_positivos_ou_negativos_devolvem_zero():
    assert tpr(MatrizDeConfusao(vp=0, fn=0, vn=1, fp=0)) == 0.0
    assert tnr(MatrizDeConfusao(vp=1, fn=0, vn=0, fp=0)) == 0.0


def test_rogan_gladen_corrige_o_vies_do_juiz():
    # juiz perfeito: o número cru é a verdade
    assert rogan_gladen(0.6, tpr=1.0, tnr=1.0) == pytest.approx(0.6)
    # juiz que aprova 90% dos bons e rejeita 80% dos ruins, observou 70% aprovados
    assert rogan_gladen(0.7, tpr=0.9, tnr=0.8) == pytest.approx((0.7 + 0.8 - 1) / (0.9 + 0.8 - 1))
    # o resultado é limitado ao intervalo [0, 1]
    assert rogan_gladen(0.05, tpr=0.9, tnr=0.8) == 0.0


def test_bootstrap_ic_e_deterministico_e_contem_a_estimativa():
    rotulos_juiz = [True] * 70 + [False] * 30

    estimativa, (baixo, alto) = bootstrap_ic(rotulos_juiz, tpr=0.9, tnr=0.8, n=200, seed=0)
    repetido, _ = bootstrap_ic(rotulos_juiz, tpr=0.9, tnr=0.8, n=200, seed=0)

    assert estimativa == repetido
    assert baixo <= estimativa <= alto
    assert 0.0 <= baixo < alto <= 1.0
