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
        preferencias_do_cliente="- Responder em maiúsculas",
        memorias="(nada)",
        resumo_da_conversa="(nenhum)",
        critica="",
    )

    assert "responder em tom formal" in texto
    assert "- Responder em maiúsculas" in texto
    assert "{{" not in texto


def _secao(texto: str, titulo: str) -> str:
    """O corpo de uma seção `## titulo`, até a próxima seção."""
    corpo = texto.split(f"## {titulo}\n", 1)[1]
    return corpo.split("\n## ", 1)[0]


@pytest.mark.parametrize("nome", ["agente", "gerar_resposta"])
def test_preferencias_do_cliente_tem_secao_propria_abaixo_das_instrucoes_do_atendente(nome):
    texto = carregar_prompt(nome).texto
    titulo_do_atendente = "## Instruções do Atendente para este Cliente (Memória Procedural)"
    titulo_do_cliente = "## Preferências do Cliente sobre a forma de falar"

    assert titulo_do_atendente in texto
    assert texto.index(titulo_do_atendente) < texto.index(titulo_do_cliente)
    secao = _secao(texto, "Preferências do Cliente sobre a forma de falar")
    assert "{{preferencias_do_cliente}}" in secao
    assert "{{memoria_procedural}}" not in secao
    assert "só para a forma" in secao
    assert "nunca mudam a política, os preços, os prazos" in secao
    assert "instruções do Atendente valem mais" in secao
    assert "ignore essa preferência" in secao


def test_extrator_de_memorias_recebe_preferencias_atuais_e_ultima_mensagem():
    prompt = carregar_prompt("extrair_memorias")

    assert prompt.variaveis == {
        "preferencias_atuais",
        "ultima_mensagem_do_cliente",
        "fatos_conhecidos",
        "conversa",
    }
    assert "3. preferencias" in prompt.texto
    assert "null" in prompt.texto


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
