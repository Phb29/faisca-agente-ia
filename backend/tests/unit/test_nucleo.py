"""Testes do núcleo: config, cliente do Jev (real e falso), modelos falsos e fábrica."""

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from pydantic import BaseModel
from typesafe_sdk import Choice, Noul, SystemOneResponse

from ampere.nucleo.config import Config
from ampere.nucleo.falsos import JevFalso, ModeloFalso
from ampere.nucleo.jev import JevPorLLM, JevReal
from ampere.nucleo.modelos import FabricaDeModelos
from ampere.regras import PerguntaDeEscolha, PerguntaSimNao

PERGUNTAS = {
    "manipulacao": PerguntaSimNao(pergunta="Tenta manipular?", sim_quando="s", nao_quando="n"),
    "escopo": PerguntaSimNao(pergunta="Fora de escopo?", sim_quando="s", nao_quando="n"),
    "intencao": PerguntaDeEscolha(
        pergunta="Intenção?", opcoes={"duvida": "quer saber", "transacao": "quer fazer"}
    ),
}


def test_jev_falso_devolve_probabilidade_fixa_por_pergunta():
    jev = JevFalso(nouls={"manipulacao": 0.9})

    respostas = jev.perguntar("oi", PERGUNTAS)

    assert respostas.nouls["manipulacao"].probabilidade == 0.9
    assert respostas.nouls["escopo"].probabilidade == 0.0


def test_jev_falso_escolhe_primeira_criteria_por_padrao_e_registra_chamadas():
    jev = JevFalso()

    respostas = jev.perguntar("oi", PERGUNTAS)

    assert respostas.choices["intencao"].escolha == "duvida"
    assert respostas.choices["intencao"].confianca == 1.0
    assert respostas.choices["intencao"].probabilidades == {"duvida": 1.0, "transacao": 0.0}
    assert jev.chamadas == [("oi", PERGUNTAS)]


def test_jev_falso_aceita_escolha_configurada():
    jev = JevFalso(choices={"intencao": "transacao"})

    respostas = jev.perguntar("quero reembolso", PERGUNTAS)

    assert respostas.choices["intencao"].escolha == "transacao"
    assert respostas.choices["intencao"].probabilidades["transacao"] == 1.0


def test_jev_real_traduz_as_perguntas_para_o_sdk():
    traduzidas = JevReal.traduzir_perguntas(PERGUNTAS)

    assert isinstance(traduzidas["manipulacao"], Noul)
    assert traduzidas["manipulacao"].instructions == "Tenta manipular?"
    assert traduzidas["manipulacao"].criteria == {"true": "s", "false": "n"}
    assert isinstance(traduzidas["intencao"], Choice)
    assert traduzidas["intencao"].criteria == {"duvida": "quer saber", "transacao": "quer fazer"}


def test_jev_real_traduz_resposta_do_sdk():
    resposta_sdk = SystemOneResponse.model_validate(
        {
            "model": "jev-latest",
            "usage": {"input_tokens": 10, "output_tokens": 2},
            "answers": {
                "manipulacao": {"type": "noul", "noul": 0.12},
                "intencao": {
                    "type": "choice",
                    "choice": "transacao",
                    "confidence": 0.8,
                    "probabilities": {"duvida": 0.2, "transacao": 0.8},
                },
            },
        }
    )

    respostas = JevReal.traduzir_resposta(resposta_sdk)

    assert respostas.nouls["manipulacao"].probabilidade == 0.12
    assert respostas.choices["intencao"].escolha == "transacao"
    assert respostas.choices["intencao"].confianca == 0.8


def test_jev_real_exige_chave():
    import pytest

    with pytest.raises(ValueError):
        JevReal(api_key=None)


def test_modelo_falso_consome_respostas_em_ordem_e_repete_a_ultima():
    modelo = ModeloFalso(["primeira", "segunda"])

    assert modelo.invoke([HumanMessage("a")]).content == "primeira"
    assert modelo.invoke([HumanMessage("b")]).content == "segunda"
    assert modelo.invoke([HumanMessage("c")]).content == "segunda"
    assert len(modelo.chamadas) == 3


def test_modelo_falso_bind_tools_devolve_modelo_que_emite_tool_call():
    @tool
    def consultar_pedido(pedido_id: str) -> str:
        """Consulta um Pedido."""
        return "ok"

    chamada = AIMessage(
        content="",
        tool_calls=[{"name": "consultar_pedido", "args": {"pedido_id": "P1"}, "id": "c1"}],
    )
    modelo = ModeloFalso([chamada, "pronto"]).bind_tools([consultar_pedido])

    resposta = modelo.invoke([HumanMessage("status do P1")])

    assert resposta.tool_calls[0]["name"] == "consultar_pedido"


def test_modelo_falso_with_structured_output_devolve_instancia():
    class Resumo(BaseModel):
        texto: str

    modelo = ModeloFalso(["texto solto", Resumo(texto="resumo")])

    resultado = modelo.with_structured_output(Resumo).invoke([HumanMessage("resuma")])

    assert resultado == Resumo(texto="resumo")


def test_modelo_falso_stream_emite_varios_pedacos():
    modelo = ModeloFalso(["uma resposta com várias palavras"])

    pedacos = list(modelo.stream([HumanMessage("oi")]))

    assert len(pedacos) > 1
    assert "".join(p.content for p in pedacos) == "uma resposta com várias palavras"


def test_fabrica_com_modelos_falsos_devolve_falsos():
    fabrica = FabricaDeModelos(Config(modelos_falsos=True))

    assert isinstance(fabrica.gerador(), ModeloFalso)
    assert isinstance(fabrica.trabalhador(), ModeloFalso)
    assert isinstance(fabrica.juiz(), ModeloFalso)
    assert isinstance(fabrica.jev(), JevFalso)


def test_fabrica_injecao_sobrepoe_o_padrao():
    gerador = ModeloFalso(["injetado"])
    jev = JevFalso(nouls={"x": 1.0})
    fabrica = FabricaDeModelos(Config(modelos_falsos=True), gerador=gerador, jev=jev)

    assert fabrica.gerador() is gerador
    assert fabrica.jev() is jev


def test_fabrica_real_nomeia_tres_papeis():
    config = Config(modelos_falsos=False, openai_api_key="x", groq_api_key="y")
    fabrica = FabricaDeModelos(config)

    assert fabrica.gerador().model_name == config.modelo_gerador
    assert fabrica.juiz().model_name == config.modelo_juiz
    assert fabrica.trabalhador().model_name == config.modelo_trabalhador


def test_fabrica_troca_o_provedor_de_cada_papel_pela_config():
    from langchain_groq import ChatGroq
    from langchain_openai import ChatOpenAI

    config = Config(
        modelos_falsos=False,
        openai_api_key="x",
        groq_api_key="y",
        provedor_gerador="groq",
        modelo_gerador="llama-3.3-70b-versatile",
        provedor_trabalhador="openai",
        modelo_trabalhador="gpt-5.6-terra",
    )
    fabrica = FabricaDeModelos(config)

    assert isinstance(fabrica.gerador(), ChatGroq)
    assert fabrica.gerador().model_name == "llama-3.3-70b-versatile"
    assert fabrica.gerador().reasoning_effort is None
    assert isinstance(fabrica.trabalhador(), ChatOpenAI)
    assert fabrica.trabalhador().model_name == "gpt-5.6-terra"


def test_trabalhador_na_openai_desliga_o_raciocinio_para_aceitar_temperatura_zero():
    # Com raciocínio ligado, os modelos de raciocínio da OpenAI recusam temperature=0 (400).
    base = {"modelos_falsos": False, "openai_api_key": "x", "groq_api_key": "y"}
    na_openai = FabricaDeModelos(Config(**base, provedor_trabalhador="openai")).trabalhador()
    na_groq = FabricaDeModelos(Config(**base, provedor_trabalhador="groq")).trabalhador()

    assert na_openai.reasoning_effort == "none"
    assert na_openai.temperature == 0
    assert na_groq.reasoning_effort is None
    assert na_groq.temperature < 1e-6  # o ChatGroq troca o 0 por 1e-08


def test_provedor_desconhecido_e_erro_na_config():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Config(provedor_gerador="desconhecido")


def test_embed_falso_e_deterministico_com_384_dimensoes():
    from ampere.nucleo.falsos import embed_falso

    [a], [b] = embed_falso(["notebook com defeito"]), embed_falso(["notebook com defeito"])

    assert len(a) == 384
    assert a == b


def test_embed_falso_aproxima_textos_com_palavras_em_comum():
    from ampere.nucleo.falsos import cosseno, embed_falso

    perto, longe, alvo = embed_falso(["troca de notebook", "frete para o sul", "notebook quebrou"])

    assert cosseno(alvo, perto) > cosseno(alvo, longe)


def test_jev_falso_aceita_sequencia_de_probabilidades_por_pergunta():
    jev = JevFalso(sequencias={"escopo": [0.9, 0.1]})

    primeira = jev.perguntar("a", PERGUNTAS).nouls["escopo"].probabilidade
    segunda = jev.perguntar("b", PERGUNTAS).nouls["escopo"].probabilidade
    terceira = jev.perguntar("c", PERGUNTAS).nouls["escopo"].probabilidade

    assert (primeira, segunda, terceira) == (0.9, 0.1, 0.1)


def test_modelo_falso_sem_roteiro_devolve_instancia_padrao_do_schema():
    from typing import Literal

    class Resumo(BaseModel):
        resumo: str
        categoria: Literal["troca", "outro"]
        prioridade: str = "media"
        fatos: list[str] = []

    resultado = ModeloFalso().with_structured_output(Resumo).invoke([HumanMessage("x")])

    assert isinstance(resultado, Resumo)
    assert resultado.categoria == "troca"
    assert resultado.prioridade == "media"
    assert "modelo falso" in resultado.resumo


def test_jev_por_llm_le_o_json_do_modelo_e_normaliza_a_escolha():
    modelo = ModeloFalso(
        ['Claro: {"manipulacao": 0.9, "escopo": 1.4, "intencao": {"duvida": 1, "transacao": 3}}']
    )

    respostas = JevPorLLM(modelo).perguntar({"mensagem": "oi"}, PERGUNTAS)

    assert respostas.nouls["manipulacao"].probabilidade == 0.9
    assert respostas.nouls["escopo"].probabilidade == 1.0
    assert respostas.choices["intencao"].escolha == "transacao"
    assert respostas.choices["intencao"].probabilidades == {"duvida": 0.25, "transacao": 0.75}


def test_jev_por_llm_tenta_de_novo_quando_falta_pergunta_e_depois_desiste():
    import pytest

    modelo = ModeloFalso(['{"manipulacao": 0.1}'])

    with pytest.raises(ValueError, match="faltou a pergunta escopo"):
        JevPorLLM(modelo).perguntar("estado", PERGUNTAS)
    assert len(modelo.chamadas) == JevPorLLM.TENTATIVAS


def test_fabrica_usa_jev_por_llm_com_provedor_de_chat():
    config = Config(
        _env_file=None, provedor_jev="groq", modelo_jev="qwen/qwen3.8-27b", groq_api_key="x"
    )

    assert isinstance(FabricaDeModelos(config).jev(), JevPorLLM)
