"""Partes puras dos evals: parse dos CSVs, comparação por código, divisão estratificada,
agregação de métricas e calibração do juiz, tudo com falsos. Os evals de verdade (modelos
reais) rodam por `ampere-evals`, fora do pytest."""

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from ampere.evals import agente, calibracao, conjuntos, rag
from ampere.evals.juiz import (
    Exemplo,
    Veredito,
    formatar_few_shot,
    julgar_fidelidade,
    julgar_relevancia,
    julgar_resolucao,
)
from ampere.evals.metricas import MatrizDeConfusao
from ampere.nucleo.config import Config
from ampere.nucleo.falsos import JevFalso, ModeloFalso
from ampere.prompts import NOMES, carregar_prompt
from ampere.rag.busca import RetrieverFalso
from ampere.rag.chunkers import Chunk
from tests.apoio import composicao_falsa, tool_call

PASTA_DADOS = Path(__file__).parents[2] / "ampere" / "evals" / "dados"


def chunk(documento: str, texto: str = "trecho") -> Chunk:
    return Chunk(
        texto=texto,
        documento=documento,
        categoria="garantia",
        produto="notebooks",
        vigencia="2026-01-01",
        tipo="politica",
        indice=0,
    )


def cenario(**extras) -> agente.Cenario:
    base = dict(
        id="c1",
        mensagem="qual a garantia do notebook?",
        cliente_id="cli_ana",
        pedido_id=None,
        memorias="",
        intencao_esperada="duvida",
        acao_esperada="consultar_base_de_conhecimento",
        desfecho_esperado="Resolvida",
        guardrail_bloqueia=False,
    )
    return agente.Cenario(**{**base, **extras})


def rotulo(aprovada: bool, n: int = 0) -> calibracao.Rotulo:
    return calibracao.Rotulo(
        mensagem=f"mensagem {n}",
        resposta=f"resposta {n}",
        aprovada=aprovada,
        critica="ok" if aprovada else "promete fora da política",
    )


# --- prompts e juiz ---------------------------------------------------------------------------


@pytest.mark.parametrize("nome", [n for n in NOMES if n.startswith("juiz_")])
def test_prompts_do_juiz_tem_nome_versao_e_texto(nome):
    prompt = carregar_prompt(nome)

    assert prompt.nome == nome
    assert prompt.versao
    assert "aprovada" in prompt.texto and "critica" in prompt.texto


def test_few_shot_e_renderizado_em_blocos():
    texto = formatar_few_shot(
        [Exemplo(mensagem="m1", resposta="r1", rotulo=True, critica="boa")],
    )

    assert "Mensagem: m1" in texto
    assert "Resposta: r1" in texto
    assert "Rótulo: Aprovada" in texto
    assert "Crítica: boa" in texto
    assert formatar_few_shot([]) == "(nenhum exemplo)"


def test_julgar_resolucao_poe_few_shot_mensagem_e_resposta_no_prompt():
    juiz = ModeloFalso([Veredito(aprovada=False, critica="prometeu prazo")])
    exemplo = Exemplo(mensagem="m1", resposta="r1", rotulo=False, critica="inventou")

    veredito = julgar_resolucao(
        juiz, mensagem="quero reembolso", resposta="cai amanhã", few_shot=[exemplo]
    )

    assert veredito == Veredito(aprovada=False, critica="prometeu prazo")
    sistema, humano = juiz.chamadas[0]
    assert "Rótulo: Reprovada" in sistema.content
    assert "quero reembolso" in humano.content and "cai amanhã" in humano.content


def test_julgar_fidelidade_e_relevancia_levam_contexto_e_pergunta():
    juiz = ModeloFalso([Veredito(aprovada=True, critica="fiel")])

    fidelidade = julgar_fidelidade(
        juiz, pergunta="garantia?", contexto=["12 meses", "24 meses"], resposta="12 meses"
    )
    relevancia = julgar_relevancia(juiz, pergunta="garantia?", resposta="12 meses")

    assert fidelidade.aprovada and relevancia.aprovada
    assert "24 meses" in juiz.chamadas[0][1].content
    assert "garantia?" in juiz.chamadas[1][1].content


# --- eval do RAG ------------------------------------------------------------------------------


def test_avaliar_retrieval_no_nivel_do_documento():
    retriever = RetrieverFalso([chunk("frete.md"), chunk("garantia.md"), chunk("garantia.md")])
    golden = [
        rag.LinhaRag(
            pergunta="p1", documento_esperado="garantia.md", resposta_referencia="", origem="manual"
        ),
        rag.LinhaRag(
            pergunta="p2", documento_esperado="troca.md", resposta_referencia="", origem="manual"
        ),
        rag.LinhaRag(
            pergunta="p3", documento_esperado="frete.md", resposta_referencia="", origem="manual"
        ),
    ]

    resultado = rag.avaliar_retrieval(retriever, golden, k=5)

    assert resultado.n == 3
    assert resultado.recall_at_5 == pytest.approx(2 / 3)
    assert resultado.mrr == pytest.approx((0.5 + 0.0 + 1.0) / 3)
    assert resultado.por_pergunta[0].recuperados == ["frete.md", "garantia.md"]
    assert retriever.perguntas == ["p1", "p2", "p3"]


def test_avaliar_retrieval_respeita_o_k():
    retriever = RetrieverFalso([chunk("a.md"), chunk("b.md")])
    golden = [
        rag.LinhaRag(pergunta="p", documento_esperado="b.md", resposta_referencia="", origem="m")
    ]

    assert rag.avaliar_retrieval(retriever, golden, k=1).recall_at_5 == 0.0


def test_avaliar_geracao_usa_o_prompt_do_grafo_e_julga_duas_vezes():
    gerador = ModeloFalso(["A garantia é de 12 meses."])
    juiz = ModeloFalso(
        [Veredito(aprovada=True, critica="fiel"), Veredito(aprovada=False, critica="vago")]
    )
    retriever = RetrieverFalso([chunk("garantia.md", "A garantia de notebooks é de 12 meses.")])
    golden = [
        rag.LinhaRag(
            pergunta="garantia?",
            documento_esperado="garantia.md",
            resposta_referencia="12 meses",
            origem="m",
        ),
        rag.LinhaRag(
            pergunta="frete?", documento_esperado="frete.md", resposta_referencia="", origem="m"
        ),
    ]

    resultado = rag.avaliar_geracao(gerador, juiz, retriever, golden, amostra=1)

    assert resultado.n == 1
    assert resultado.fidelidade == 1.0
    assert resultado.relevancia == 0.0
    assert resultado.vereditos[0].resposta == "A garantia é de 12 meses."
    prompt_do_gerador = gerador.chamadas[0][0].content
    assert "[garantia.md] A garantia de notebooks é de 12 meses." in prompt_do_gerador
    assert "Ampère" in prompt_do_gerador


class QdrantFalso:
    def __init__(self, colecoes: set[str]) -> None:
        self.colecoes = colecoes

    def collection_exists(self, nome: str) -> bool:
        return nome in self.colecoes


def test_variantes_disponiveis_pula_colecao_ausente_openai_sem_chave_e_sq_sem_trabalhador():
    client = QdrantFalso({"politicas__minilm__markdown", "politicas__openai__markdown"})

    sem_chaves = rag.variantes_disponiveis(client, Config(modelos_falsos=False))
    com_groq = rag.variantes_disponiveis(client, Config(modelos_falsos=False, groq_api_key="g"))
    com_tudo = rag.variantes_disponiveis(
        client, Config(modelos_falsos=False, groq_api_key="g", openai_api_key="o")
    )

    assert [v.nome for v in sem_chaves] == [
        "minilm+markdown+colbert+sem-sq",
        "minilm+markdown+nenhum+sem-sq",
    ]
    assert len(com_groq) == 4 and all(v.embedder == "minilm" for v in com_groq)
    assert len(com_tudo) == 8 and {v.embedder for v in com_tudo} == {"minilm", "openai"}


# --- eval do agente ---------------------------------------------------------------------------


def estado(**campos) -> dict:
    base = {
        "messages": [HumanMessage("oi"), AIMessage("resposta")],
        "intencao": "duvida",
        "acoes_tomadas": ["consultar_base_de_conhecimento"],
        "desfecho": "Resolvida",
        "bloqueio": None,
    }
    return {**base, **campos}


def test_comparar_acerto_total():
    comparacao = agente.comparar(cenario(), estado())

    assert comparacao.intencao_ok and comparacao.acao_ok and comparacao.desfecho_ok
    assert (comparacao.intencao, comparacao.acao, comparacao.desfecho) == (
        "duvida",
        "consultar_base_de_conhecimento",
        "Resolvida",
    )
    assert comparacao.bloqueado is False


def test_comparar_acao_errada_e_nenhuma_acao():
    errada = agente.comparar(cenario(), estado(acoes_tomadas=["consultar_pedido", "abrir_ticket"]))
    nenhuma = agente.comparar(cenario(acao_esperada="nenhuma"), estado(acoes_tomadas=[]))

    assert errada.acao == "consultar_pedido" and not errada.acao_ok
    assert errada.intencao_ok and errada.desfecho_ok
    assert nenhuma.acao == "nenhuma" and nenhuma.acao_ok


def test_comparar_detecta_aprovacao_pendente_pela_interrupcao():
    esperado = cenario(
        intencao_esperada="transacao",
        acao_esperada="emitir_reembolso",
        desfecho_esperado="Aprovação Pendente",
    )
    interrompido = estado(
        intencao="transacao",
        acoes_tomadas=["emitir_reembolso"],
        desfecho=None,
        __interrupt__=[object()],
    )

    comparacao = agente.comparar(esperado, interrompido)

    assert comparacao.desfecho == "Aprovação Pendente"
    assert comparacao.intencao_ok and comparacao.acao_ok and comparacao.desfecho_ok


def test_comparar_conta_a_acao_presa_no_gate_como_tomada():
    esperado = cenario(
        intencao_esperada="transacao",
        acao_esperada="emitir_reembolso",
        desfecho_esperado="Aprovação Pendente",
    )
    interrompido = estado(
        intencao="transacao",
        acoes_tomadas=[],
        desfecho=None,
        messages=[
            HumanMessage("quero reembolso"),
            tool_call("emitir_reembolso", {"pedido_id": "P1"}),
        ],
        __interrupt__=[object()],
    )

    comparacao = agente.comparar(esperado, interrompido)

    assert comparacao.acao == "emitir_reembolso"
    assert comparacao.acao_ok
    assert comparacao.desfecho == "Aprovação Pendente"


def test_comparar_nao_conta_tool_call_pendente_sem_interrupcao():
    esperado = cenario(acao_esperada="emitir_reembolso")
    sem_interrupcao = estado(
        acoes_tomadas=[],
        messages=[
            HumanMessage("quero reembolso"),
            tool_call("emitir_reembolso", {"pedido_id": "P1"}),
        ],
    )

    comparacao = agente.comparar(esperado, sem_interrupcao)

    assert comparacao.acao == "nenhuma"
    assert not comparacao.acao_ok


def test_comparar_cenario_bloqueado_pelo_guardrail():
    bloqueado = cenario(
        intencao_esperada=None,
        acao_esperada="nenhuma",
        desfecho_esperado="Resolvida",
        guardrail_bloqueia=True,
    )

    ok = agente.comparar(bloqueado, estado(intencao=None, acoes_tomadas=[], bloqueio="manipulacao"))
    passou_direto = agente.comparar(bloqueado, estado(intencao="duvida", acoes_tomadas=[]))

    assert ok.bloqueado and ok.intencao_ok and ok.acao_ok and ok.desfecho_ok
    assert not passou_direto.bloqueado and not passou_direto.intencao_ok


def test_resposta_final_e_a_ultima_mensagem_do_assistente_ou_vazia():
    assert agente.resposta_final(estado()) == "resposta"
    assert (
        agente.resposta_final({"messages": [HumanMessage("oi"), AIMessage("", tool_calls=[])]})
        == ""
    )


def test_interpretar_memorias_separa_procedural_de_semantica():
    simples = agente.interpretar_memorias(
        "Cliente teve Reembolso do Pedido P3001 há menos de 30 dias."
    )
    mista = agente.interpretar_memorias(
        "Memória Procedural: responder de forma curta. "
        "Memória Semântica: prefere ser chamada de Ana."
    )

    assert simples.semantica == ["Cliente teve Reembolso do Pedido P3001 há menos de 30 dias."]
    assert simples.procedural == ""
    assert mista.procedural == "responder de forma curta."
    assert mista.semantica == ["prefere ser chamada de Ana."]
    assert agente.interpretar_memorias("") == agente.MemoriasIniciais(semantica=[], procedural="")


# --- calibração -------------------------------------------------------------------------------


def test_dividir_e_deterministico_estratificado_e_cobre_tudo():
    rotulos = [rotulo(True, i) for i in range(12)] + [rotulo(False, i + 12) for i in range(8)]

    divisao = calibracao.dividir(rotulos, seed=0)
    repetida = calibracao.dividir(rotulos, seed=0)
    outra = calibracao.dividir(rotulos, seed=1)

    assert divisao == repetida
    assert divisao != outra
    conjuntos = [divisao.treino, divisao.dev, divisao.teste]
    assert [len(c) for c in conjuntos] == [8, 6, 6]
    todos = [r for c in conjuntos for r in c]
    assert sorted(r.mensagem for r in todos) == sorted(r.mensagem for r in rotulos)
    for conjunto in conjuntos:
        proporcao = sum(r.aprovada for r in conjunto) / len(conjunto)
        assert proporcao == pytest.approx(0.6, abs=0.1)


def test_calibrar_devolve_matriz_desacordos_e_correcao():
    divisao = calibracao.Divisao(
        treino=[rotulo(True, 0), rotulo(False, 1)],
        dev=[rotulo(True, 2), rotulo(True, 3), rotulo(False, 4), rotulo(False, 5)],
        teste=[rotulo(True, 6), rotulo(False, 7)],
    )
    vereditos_dev = [
        Veredito(aprovada=True, critica="boa"),
        Veredito(aprovada=False, critica="juiz reprovou uma boa"),
        Veredito(aprovada=False, critica="ruim"),
        Veredito(aprovada=False, critica="ruim"),
    ]
    vereditos_teste = [
        Veredito(aprovada=True, critica="boa"),
        Veredito(aprovada=True, critica="fp"),
    ]
    juiz = ModeloFalso([*vereditos_dev, *vereditos_teste])

    resultado = calibracao.calibrar(juiz, divisao, n_bootstrap=50)

    assert resultado.dev.matriz == MatrizDeConfusao(vp=1, fn=1, vn=2, fp=0)
    assert resultado.dev.tpr == pytest.approx(0.5)
    assert resultado.dev.tnr == pytest.approx(1.0)
    assert resultado.dev.concordancia == pytest.approx(0.75)
    assert len(resultado.dev.desacordos) == 1
    desacordo = resultado.dev.desacordos[0]
    assert desacordo.mensagem == "mensagem 3"
    assert desacordo.rotulo_humano is True and desacordo.veredito is False
    assert desacordo.critica_juiz == "juiz reprovou uma boa"
    assert desacordo.critica_humana == "ok"
    assert resultado.teste.matriz == MatrizDeConfusao(vp=1, fn=0, vn=0, fp=1)
    assert resultado.taxa_observada == pytest.approx(1.0)
    # rogan_gladen(1.0, tpr=0.5, tnr=1.0) = (1.0 + 1.0 - 1) / (0.5 + 1.0 - 1) = 2.0, limitado a 1.0
    assert resultado.taxa_corrigida == pytest.approx(1.0)
    assert resultado.intervalo[0] <= resultado.taxa_corrigida <= resultado.intervalo[1]
    # o few-shot (treino) entra no prompt de sistema do juiz
    assert "mensagem 0" in juiz.chamadas[0][0].content


# --- os três CSVs reais -----------------------------------------------------------------------


def exige(nome: str) -> Path:
    caminho = PASTA_DADOS / nome
    assert caminho.exists(), f"{nome} precisa existir em {PASTA_DADOS}"
    return caminho


def test_golden_rag_carrega():
    linhas = rag.carregar_golden_rag(exige("golden_rag.csv"))

    assert len(linhas) >= 30
    assert all(linha.documento_esperado.endswith(".md") for linha in linhas)
    assert {linha.origem for linha in linhas} >= {"manual"}


def test_golden_agente_carrega():
    cenarios = agente.carregar_golden_agente(exige("golden_agente.csv"))

    assert len(cenarios) >= 20
    assert len({c.id for c in cenarios}) == len(cenarios)
    assert all(
        c.desfecho_esperado in {"Resolvida", "Escalada", "Aprovação Pendente"} for c in cenarios
    )
    assert any(c.guardrail_bloqueia for c in cenarios)
    assert all(
        c.intencao_esperada in {None, "duvida", "transacao", "quer_humano"} for c in cenarios
    )


def test_rotulos_humanos_carregam_balanceados():
    rotulos = calibracao.carregar_rotulos(exige("rotulos_humanos.csv"))

    assert len(rotulos) >= 40
    aprovadas = sum(r.aprovada for r in rotulos)
    assert abs(aprovadas - (len(rotulos) - aprovadas)) <= 6


# --- os CSVs como a aba Dados da Tela de Avaliação os mostra ---------------------------------


@pytest.mark.parametrize("nome", ["rag", "agente", "juiz"])
def test_conjunto_de_dados_conta_por_grupo_e_tem_ids_unicos(nome):
    dados = conjuntos.conjunto_de_dados(nome)

    assert dados["eval"] == nome
    assert dados["arquivo"].endswith(".csv")
    assert dados["n"] == len(dados["linhas"]) > 0
    assert sum(dados["grupos"].values()) == dados["n"]
    assert len({linha["id"] for linha in dados["linhas"]}) == dados["n"]


def test_conjunto_da_busca_usa_os_ids_e_grupos_das_execucoes():
    golden = rag.carregar_golden_rag()
    dados = conjuntos.conjunto_de_dados("rag")

    primeira = dados["linhas"][0]
    assert primeira["id"] == rag.id_da_pergunta(0)
    assert primeira["grupo"] == golden[0].origem
    assert primeira["pergunta"] == golden[0].pergunta
    assert primeira["documento_esperado"] == golden[0].documento_esperado
    assert set(dados["grupos"]) == {"manual", "adversarial"}


def test_conjunto_do_agente_agrupa_como_a_amostra():
    cenarios = agente.carregar_golden_agente()
    dados = conjuntos.conjunto_de_dados("agente")

    for cenario, linha in zip(cenarios, dados["linhas"], strict=True):
        assert linha["id"] == cenario.id
        assert linha["grupo"] == agente.grupo_do_cenario(cenario)
        assert linha["desfecho_esperado"] == cenario.desfecho_esperado
    bloqueados = [linha for linha in dados["linhas"] if linha["guardrail_bloqueia"]]
    assert bloqueados and all(linha["grupo"] == "bloqueio" for linha in bloqueados)


def test_conjunto_do_juiz_marca_treino_dev_e_teste_da_mesma_divisao():
    rotulos = calibracao.carregar_rotulos()
    divisao = calibracao.dividir(rotulos, seed=calibracao.SEED_DA_AMOSTRA)
    dados = conjuntos.conjunto_de_dados("juiz")

    por_id = {linha["id"]: linha for linha in dados["linhas"]}
    for nome_do_conjunto in ("treino", "dev", "teste"):
        for r in getattr(divisao, nome_do_conjunto):
            assert por_id[calibracao.id_do_rotulo(r)]["conjunto"] == nome_do_conjunto
    assert dados["conjuntos"] == {
        "treino": len(divisao.treino),
        "dev": len(divisao.dev),
        "teste": len(divisao.teste),
    }
    assert {linha["grupo"] for linha in dados["linhas"]} == {"aprovada", "reprovada"}


def test_conjunto_de_eval_desconhecido_e_erro():
    with pytest.raises(ValueError):
        conjuntos.conjunto_de_dados("outro")


# --- um cenário de ponta a ponta (a borda entre o eval e o grafo) ----------------------------


def test_executar_cenario_roda_o_grafo_compara_e_pede_veredito_ao_juiz():
    config = Config(modelos_falsos=True)
    composicao = composicao_falsa(
        gerador=["A garantia de notebooks é de 12 meses."],
        juiz=[Veredito(aprovada=True, critica="resolveu")],
        jev=JevFalso(choices={"intencao": "duvida"}),
        config=config,
    )

    cenario = agente.Cenario(
        id="duvida-01",
        mensagem="qual a garantia do notebook?",
        cliente_id="cli_ana",
        intencao_esperada="duvida",
        acao_esperada="consultar_base_de_conhecimento",
        desfecho_esperado="Resolvida",
    )

    resultado = agente.ExecutorDeCenarios(config, composicao).executar(cenario)

    assert resultado.comparacao.tudo_ok
    assert resultado.resposta == "A garantia de notebooks é de 12 meses."
    assert resultado.veredito == Veredito(aprovada=True, critica="resolveu")
