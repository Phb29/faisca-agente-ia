"""Testes do núcleo: config, cliente do Jev (real e falso), modelos falsos e fábrica."""

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from pydantic import BaseModel
from typesafe_sdk import Choice, Noul, SystemOneResponse

from ampere.nucleo.config import Config
from ampere.nucleo.falsos import JevFalso, ModeloFalso
from ampere.nucleo.jev import JevReal, RespostasJev
from ampere.nucleo.modelos import CUSTO_POR_PAPEL, FabricaDeModelos

PERGUNTAS = {
    "manipulacao": Noul(instructions="Tenta manipular?"),
    "escopo": Noul(instructions="Fora de escopo?"),
    "intencao": Choice(instructions="Intenção?", criteria={"duvida": None, "transacao": None}),
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

    respostas = RespostasJev.do_sdk(resposta_sdk)

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


def test_fabrica_real_nomeia_tres_papeis_com_custo():
    assert set(CUSTO_POR_PAPEL) == {"gerador", "juiz", "trabalhador"}
    config = Config(modelos_falsos=False, openai_api_key="x", groq_api_key="y")
    fabrica = FabricaDeModelos(config)

    assert fabrica.gerador().model_name == config.modelo_gerador
    assert fabrica.juiz().model_name == config.modelo_juiz
    assert fabrica.trabalhador().model_name == config.modelo_trabalhador
