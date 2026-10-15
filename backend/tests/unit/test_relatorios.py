"""Relatórios dos evals (o que vira uma Execução) e os casos da amostra ao vivo."""

import random

import pytest

from ampere.evals import agente, rag
from ampere.evals.juiz import Veredito
from ampere.evals.relatorio import Sorteado, caso_com_erro, consumir, contexto_base, media
from ampere.nucleo.config import Config
from ampere.nucleo.falsos import JevFalso, ModeloFalso
from ampere.rag.busca import RetrieverFalso
from ampere.rag.chunkers import Chunk
from tests.apoio import composicao_falsa, tool_call


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


# --- agente -----------------------------------------------------------------------------------


def cenario_ag(id: str, intencao: str | None, *, bloqueia: bool = False, **extras):
    base = dict(
        id=id,
        mensagem=f"mensagem {id}",
        cliente_id="cli_ana",
        intencao_esperada=intencao,
        acao_esperada="consultar_base_de_conhecimento",
        desfecho_esperado="Resolvida",
        guardrail_bloqueia=bloqueia,
    )
    return agente.Cenario(**{**base, **extras})


def test_grupo_do_cenario_e_bloqueio_ou_a_intencao_esperada():
    assert agente.grupo_do_cenario(cenario_ag("b", None, bloqueia=True)) == "bloqueio"
    assert agente.grupo_do_cenario(cenario_ag("d", "duvida")) == "duvida"
    assert agente.grupo_do_cenario(cenario_ag("q", "quer_humano")) == "quer_humano"


def test_sortear_amostra_do_agente_pega_um_de_cada_grupo():
    cenarios = [
        cenario_ag("d1", "duvida"),
        cenario_ag("d2", "duvida"),
        cenario_ag("t1", "transacao"),
        cenario_ag("q1", "quer_humano"),
        cenario_ag("b1", None, bloqueia=True),
    ]

    for seed in range(8):
        sorteados = agente.sortear_amostra(random.Random(seed), cenarios)

        assert [s.grupo for s in sorteados][:2] == ["duvida", "transacao"]
        assert sorteados[2].grupo in {"bloqueio", "quer_humano"}
        assert all(s.id == s.item.id and s.texto == s.item.mensagem for s in sorteados)


def test_sortear_amostra_do_agente_funciona_com_o_golden_real():
    assert len(agente.sortear_amostra(random.Random(1))) == 3


def test_caso_e_resumo_do_agente():
    certo = agente.ResultadoDoCenario(
        cenario=cenario_ag("ag01", "duvida"),
        comparacao=agente.Comparacao(
            intencao_ok=True,
            acao_ok=True,
            desfecho_ok=True,
            intencao="duvida",
            acao="consultar_base_de_conhecimento",
            desfecho="Resolvida",
            bloqueado=False,
        ),
        resposta="12 meses.",
        veredito=Veredito(aprovada=True, critica="resolveu"),
        caminho=["carregar_memoria", "roteador"],
        duracao_s=2.345,
    )
    errado = agente.ResultadoDoCenario(
        cenario=cenario_ag("ag11", "transacao", acao_esperada="emitir_reembolso"),
        comparacao=agente.Comparacao(
            intencao_ok=True,
            acao_ok=False,
            desfecho_ok=False,
            intencao="transacao",
            acao="consultar_pedido",
            desfecho="Resolvida",
            bloqueado=False,
        ),
        resposta="Quer que eu peça o reembolso?",
        veredito=None,
    )

    caso = agente.caso_agente(certo)
    resumo = agente.resumo_agente(
        [caso, agente.caso_agente(errado), {"id": "ag16", "erro": "Jev fora"}]
    )

    assert caso["id"] == "ag01"
    assert caso["texto"] == "mensagem ag01"
    assert caso["grupo"] == "duvida"
    assert caso["esperado"] == {
        "intencao": "duvida",
        "acao": "consultar_base_de_conhecimento",
        "desfecho": "Resolvida",
    }
    assert caso["ok"] == {"intencao": True, "acao": True, "desfecho": True}
    assert caso["caminho"] == ["carregar_memoria", "roteador"]
    assert caso["juiz"] == {"aprovada": True, "critica": "resolveu"}
    assert caso["duracao_s"] == 2.35
    assert resumo == {
        "n": 2,
        "erros": 1,
        "intencao": 1.0,
        "acao": 0.5,
        "desfecho": 0.5,
        "tudo": 0.5,
        "juiz_aprovadas": 1,
        "julgados": 1,
    }


def test_passos_do_cenario_soltam_cada_no_e_o_juiz_e_guardam_o_caminho():
    composicao = composicao_falsa(
        gerador=["A garantia de notebooks é de 12 meses."],
        juiz=[Veredito(aprovada=True, critica="resolveu")],
    )
    cenario = cenario_ag("duvida-01", "duvida", mensagem="qual a garantia do notebook?")

    fases, resultado = rodar_passos(
        agente.ExecutorDeCenarios(Config(modelos_falsos=True), composicao).passos(cenario)
    )

    assert fases[0] == "carregar_memoria"
    assert fases[-1] == "juiz"
    assert fases[:-1] == resultado.caminho
    assert "gerar_resposta" in resultado.caminho
    assert resultado.comparacao.tudo_ok
    assert resultado.veredito == Veredito(aprovada=True, critica="resolveu")
    assert resultado.duracao_s > 0


def test_passos_do_cenario_veem_a_interrupcao_do_gate_como_aprovacao_pendente():
    composicao = composicao_falsa(
        gerador=[tool_call("emitir_reembolso", {"pedido_id": "P1001", "motivo": "tela"})],
        jev=JevFalso(choices={"intencao": "transacao"}),
    )
    cenario = cenario_ag(
        "ag11",
        "transacao",
        mensagem="Quero o reembolso do pedido P1001",
        acao_esperada="emitir_reembolso",
        desfecho_esperado="Aprovação Pendente",
    )

    fases, resultado = rodar_passos(
        agente.ExecutorDeCenarios(Config(modelos_falsos=True), composicao).passos(cenario)
    )

    assert resultado.comparacao.desfecho == "Aprovação Pendente"
    assert resultado.comparacao.desfecho_ok
    assert "__interrupt__" not in resultado.caminho
    assert "juiz" not in fases, "sem resposta final, o juiz não tem o que ler"


def test_caso_ao_vivo_do_agente_devolve_o_caso_pronto():
    composicao = composicao_falsa(
        gerador=["12 meses."], juiz=[Veredito(aprovada=True, critica="ok")]
    )
    cenario = cenario_ag("ag01", "duvida", mensagem="qual a garantia do notebook?")
    sorteado = Sorteado(id="ag01", texto=cenario.mensagem, grupo="duvida", item=cenario)
    executor = agente.ExecutorDeCenarios(Config(modelos_falsos=True), composicao)

    fases, caso = rodar_passos(agente.caso_ao_vivo(sorteado, executor))

    assert fases[-1] == "juiz"
    assert caso["id"] == "ag01"
    assert caso["juiz"] == {"aprovada": True, "critica": "ok"}
