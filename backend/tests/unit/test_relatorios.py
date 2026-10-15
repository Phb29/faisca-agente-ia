"""Relatórios dos evals (o que vira uma Execução) e os casos da amostra ao vivo."""

import pytest

from ampere.evals.relatorio import Sorteado, caso_com_erro, consumir, contexto_base, media
from ampere.nucleo.config import Config
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
