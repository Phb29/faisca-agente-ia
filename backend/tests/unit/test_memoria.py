"""Memória de longo prazo: Store em memória, salvar e carregar por Cliente."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from ampere.memoria.carregar import carregar_memorias
from ampere.memoria.procedural import MemoriaProcedural, escrever_procedural, ler_procedural
from ampere.memoria.salvar import MemoriasExtraidas, salvar_memorias
from ampere.memoria.store import (
    criar_store_em_memoria,
    namespace_episodica,
    namespace_procedural,
    namespace_semantica,
)
from ampere.memoria.tipos import memorias_vazias
from ampere.nucleo.falsos import ModeloFalso, embed_falso

CONVERSA = [
    HumanMessage("Meu notebook Vega 15 tem frete grátis para troca?"),
    ToolMessage(content="resultado", tool_call_id="t1"),
    AIMessage(content=""),
    AIMessage("Sim, a troca tem frete grátis."),
]


def extraidas() -> MemoriasExtraidas:
    return MemoriasExtraidas(
        fatos=["Tem um notebook Vega 15"], episodio="Perguntou sobre frete; resolvido"
    )


def test_namespaces_por_cliente():
    assert namespace_semantica("cli_ana") == ("cli_ana", "semantica")
    assert namespace_episodica("cli_ana") == ("cli_ana", "episodica")
    assert namespace_procedural("cli_ana") == ("cli_ana", "procedural")


def test_salvar_e_carregar_devolve_fato_e_episodio():
    store = criar_store_em_memoria(embed_falso)
    trabalhador = ModeloFalso([extraidas()])

    resultado = salvar_memorias(
        store, trabalhador, "cli_ana", CONVERSA, desfecho="Resolvida", acoes=["consultar_base"]
    )
    memorias = carregar_memorias(store, "cli_ana", "problema no notebook")

    assert resultado == extraidas()
    assert memorias["semantica"] == ["Tem um notebook Vega 15"]
    assert len(memorias["episodica"]) == 1
    episodio = memorias["episodica"][0]
    assert episodio["resumo"] == "Perguntou sobre frete; resolvido"
    assert episodio["desfecho"] == "Resolvida"
    assert episodio["acoes"] == ["consultar_base"]
    assert episodio["data"]
    assert memorias["procedural"] == ""


def test_salvar_renderiza_prompt_com_conversa_e_fatos_conhecidos():
    store = criar_store_em_memoria(embed_falso)
    trabalhador = ModeloFalso([extraidas()])

    salvar_memorias(
        store,
        trabalhador,
        "cli_ana",
        CONVERSA,
        desfecho="Resolvida",
        acoes=[],
        fatos_conhecidos=["Mora em Curitiba"],
    )

    [chamada] = trabalhador.chamadas
    system = chamada[0].content
    assert "Cliente: Meu notebook Vega 15 tem frete grátis para troca?" in system
    assert "Assistente: Sim, a troca tem frete grátis." in system
    assert "resultado" not in system
    assert "Mora em Curitiba" in system
    assert chamada[1].content == "Extraia as memórias."


def test_salvar_sem_fatos_nao_grava_semantica():
    store = criar_store_em_memoria(embed_falso)
    trabalhador = ModeloFalso([MemoriasExtraidas(fatos=[], episodio="Só perguntou o horário")])

    salvar_memorias(store, trabalhador, "cli_ana", CONVERSA, desfecho="Resolvida", acoes=[])
    memorias = carregar_memorias(store, "cli_ana", "notebook")

    assert memorias["semantica"] == []
    assert len(memorias["episodica"]) == 1


def test_episodios_vem_do_mais_recente_para_o_mais_antigo_e_respeitam_limite():
    store = criar_store_em_memoria(embed_falso)
    for i in range(4):
        trabalhador = ModeloFalso([MemoriasExtraidas(fatos=[], episodio=f"episodio {i}")])
        salvar_memorias(store, trabalhador, "cli_ana", CONVERSA, desfecho="Resolvida", acoes=[])

    memorias = carregar_memorias(store, "cli_ana", "x", limite_episodica=3)

    resumos = [e["resumo"] for e in memorias["episodica"]]
    assert resumos == ["episodio 3", "episodio 2", "episodio 1"]


def test_procedural_roundtrip():
    store = criar_store_em_memoria(embed_falso)

    assert ler_procedural(store, "cli_ana") == ""
    escrever_procedural(store, "cli_ana", "Trate por 'senhora'.")

    assert ler_procedural(store, "cli_ana") == "Trate por 'senhora'."
    assert carregar_memorias(store, "cli_ana", "oi")["procedural"] == "Trate por 'senhora'."


def test_clientes_diferentes_nao_veem_memorias_um_do_outro():
    store = criar_store_em_memoria(embed_falso)
    salvar_memorias(
        store, ModeloFalso([extraidas()]), "cli_ana", CONVERSA, desfecho="Resolvida", acoes=[]
    )
    escrever_procedural(store, "cli_ana", "instrucao da ana")

    assert carregar_memorias(store, "cli_bruno", "problema no notebook") == memorias_vazias()


def test_cliente_sem_nada_devolve_memorias_vazias():
    store = criar_store_em_memoria(embed_falso)

    assert carregar_memorias(store, "cli_novo", "oi") == memorias_vazias()


def test_salvar_sem_guardar_fatos_grava_so_o_episodio():
    store = criar_store_em_memoria(embed_falso)

    salvar_memorias(
        store,
        ModeloFalso([extraidas()]),
        "cli_ana",
        CONVERSA,
        desfecho="Resolvida",
        acoes=[],
        guardar_fatos=False,
    )
    memorias = carregar_memorias(store, "cli_ana", "notebook")

    assert memorias["semantica"] == []
    assert len(memorias["episodica"]) == 1


def test_memoria_procedural_da_api_le_e_escreve_no_store():
    store = criar_store_em_memoria(embed_falso)
    memoria = MemoriaProcedural(store)

    memoria.escrever("cli_ana", "  Responder em tom formal.  ")

    assert memoria.ler("cli_ana") == "Responder em tom formal."
    assert ler_procedural(store, "cli_ana") == "Responder em tom formal."
