"""Prompts: um arquivo por prompt, com nome e versão, e renderização estrita."""

import pytest

from ampere.prompts import NOMES, PASTA, Prompt, carregar_prompt


@pytest.mark.parametrize("nome", NOMES)
def test_todo_prompt_tem_nome_versao_e_texto(nome):
    prompt = carregar_prompt(nome)

    assert isinstance(prompt, Prompt)
    assert prompt.nome == nome
    assert prompt.versao
    assert len(prompt.texto.strip()) > 50


def test_todo_arquivo_da_pasta_esta_na_lista():
    assert {c.stem for c in PASTA.glob("*.md") if c.stem != "README"} == set(NOMES)


def test_prompt_renderiza_todas_as_variaveis():
    prompt = carregar_prompt("agente")

    texto = prompt.renderizar(
        memoria_procedural="responder em tom formal",
        memorias="(nada)",
        resumo_da_conversa="(nenhum)",
        critica="",
    )

    assert "responder em tom formal" in texto
    assert "{{" not in texto


def test_variavel_esquecida_ou_sobrando_e_erro():
    prompt = carregar_prompt("self_querying")

    with pytest.raises(ValueError, match="faltando"):
        prompt.renderizar()
    with pytest.raises(ValueError, match="sobrando"):
        prompt.renderizar(pergunta="oi", extra="x")


def test_prompt_desconhecido_falha_cedo():
    with pytest.raises(FileNotFoundError):
        carregar_prompt("nao_existe")


def test_metadata_do_prompt_para_o_trace():
    prompt = carregar_prompt("agente")

    assert prompt.metadata() == {"prompt_nome": "agente", "prompt_versao": prompt.versao}
