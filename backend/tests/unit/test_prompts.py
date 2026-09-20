"""Cada nó do grafo tem o system prompt num arquivo próprio, com nome e versão."""

import pytest

from ampere.grafo.prompts import NOMES, Prompt, carregar_prompt


@pytest.mark.parametrize("nome", NOMES)
def test_todo_prompt_tem_nome_versao_e_texto(nome):
    prompt = carregar_prompt(nome)

    assert isinstance(prompt, Prompt)
    assert prompt.nome == nome
    assert prompt.versao
    assert len(prompt.texto.strip()) > 50


def test_prompts_cobrem_os_nos_e_tarefas_esperadas():
    assert set(NOMES) == {
        "gerar_resposta",
        "agente",
        "extrair_memorias",
        "resumir_conversa",
        "resumir_ticket",
        "self_querying",
    }


def test_prompt_renderiza_variaveis():
    prompt = carregar_prompt("gerar_resposta")

    texto = prompt.renderizar(memoria_procedural="responder em tom formal", contexto="", critica="")

    assert "responder em tom formal" in texto


def test_prompt_desconhecido_falha_cedo():
    with pytest.raises(FileNotFoundError):
        carregar_prompt("nao_existe")


def test_metadata_do_prompt_para_o_trace():
    prompt = carregar_prompt("agente")

    assert prompt.metadata() == {"prompt_nome": "agente", "prompt_versao": prompt.versao}
