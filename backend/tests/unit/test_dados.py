"""Consistência dos dados: Base de Conhecimento, seed e goldens dos evals. Sem banco."""

import csv
from collections import Counter
from pathlib import Path

import frontmatter

from ampere.loja.seed import CLIENTES, PEDIDOS, REEMBOLSOS

RAIZ = Path(__file__).resolve().parents[2] / "ampere"
PASTA_BASE = RAIZ / "rag" / "base_de_conhecimento"
PASTA_DADOS = RAIZ / "evals" / "dados"

CATEGORIAS = {"troca", "devolucao", "frete", "garantia", "pagamento", "cadastro"}
PRODUTOS = {"notebooks", "celulares", "acessorios", "todos"}
TIPOS = {"politica", "procedimento"}


def _ler_csv(nome: str) -> list[dict]:
    with open(PASTA_DADOS / nome, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_documentos_tem_frontmatter_valido_e_secoes():
    arquivos = sorted(PASTA_BASE.glob("*.md"))
    assert arquivos, "nenhum documento encontrado"
    for caminho in arquivos:
        post = frontmatter.load(caminho)
        assert set(post.metadata) == {"categoria", "produto", "vigencia", "tipo"}, caminho.name
        assert post["categoria"] in CATEGORIAS, caminho.name
        assert post["produto"] in PRODUTOS, caminho.name
        assert post["tipo"] in TIPOS, caminho.name
        assert len(str(post["vigencia"])) == 10, caminho.name
        assert post.content.lstrip().startswith("# "), caminho.name
        assert "\n## " in post.content, caminho.name
        palavras = len(post.content.split())
        assert 250 <= palavras <= 600, f"{caminho.name}: {palavras} palavras"


def test_ha_24_documentos_cobrindo_as_seis_categorias():
    arquivos = sorted(PASTA_BASE.glob("*.md"))
    assert len(arquivos) == 24
    categorias = {frontmatter.load(c)["categoria"] for c in arquivos}
    assert categorias == CATEGORIAS
    tipos = Counter(frontmatter.load(c)["tipo"] for c in arquivos)
    assert tipos["procedimento"] == 6
    for caminho in arquivos:
        post = frontmatter.load(caminho)
        assert caminho.name.startswith(f"{post['categoria']}_{post['produto']}"), caminho.name


def test_golden_rag_aponta_para_documentos_existentes():
    linhas = _ler_csv("golden_rag.csv")
    assert len(linhas) >= 45
    existentes = {c.name for c in PASTA_BASE.glob("*.md")}
    for linha in linhas:
        assert set(linha) == {"pergunta", "documento_esperado", "resposta_referencia", "origem"}
        assert linha["documento_esperado"] in existentes, linha["pergunta"]
        assert linha["origem"] in {"manual", "adversarial"}
        assert linha["pergunta"].strip() and linha["resposta_referencia"].strip()
    origens = Counter(linha["origem"] for linha in linhas)
    assert origens["manual"] >= 30
    assert origens["adversarial"] >= 15


def test_golden_agente_usa_enumeracoes_e_ids_do_seed():
    linhas = _ler_csv("golden_agente.csv")
    assert len(linhas) >= 25
    clientes = {c["id"] for c in CLIENTES}
    pedidos = {p["id"] for p in PEDIDOS}
    ids = [linha["id"] for linha in linhas]
    assert len(ids) == len(set(ids)), "ids repetidos"
    for linha in linhas:
        assert linha["intencao_esperada"] in {"duvida", "transacao", "quer_humano", ""}, linha["id"]
        assert linha["acao_esperada"] in {
            "consultar_pedido",
            "consultar_base_de_conhecimento",
            "emitir_reembolso",
            "abrir_ticket",
            "nenhuma",
        }, linha["id"]
        assert linha["desfecho_esperado"] in {"Resolvida", "Escalada", "Aprovação Pendente"}
        assert linha["guardrail_bloqueia"] in {"sim", "nao"}, linha["id"]
        assert linha["cliente_id"] in clientes, linha["id"]
        assert linha["pedido_id"] == "" or linha["pedido_id"] in pedidos, linha["id"]
        if linha["guardrail_bloqueia"] == "sim":
            assert linha["intencao_esperada"] == ""
            assert linha["acao_esperada"] == "nenhuma"
            assert linha["desfecho_esperado"] == "Resolvida"
        else:
            assert linha["intencao_esperada"] != ""
    desfechos = Counter(linha["desfecho_esperado"] for linha in linhas)
    assert desfechos["Aprovação Pendente"] >= 2
    assert desfechos["Escalada"] >= 2
    assert sum(1 for linha in linhas if linha["guardrail_bloqueia"] == "sim") >= 2


def test_rotulos_humanos_balanceados():
    linhas = _ler_csv("rotulos_humanos.csv")
    assert len(linhas) == 60
    for linha in linhas:
        assert set(linha) == {"mensagem", "resposta", "rotulo", "critica"}
        assert linha["rotulo"] in {"Aprovada", "Reprovada"}
        assert linha["critica"].strip()
    rotulos = Counter(linha["rotulo"] for linha in linhas)
    assert rotulos == {"Aprovada": 30, "Reprovada": 30}


def test_seed_consistente():
    ids_clientes = {c["id"] for c in CLIENTES}
    assert ids_clientes == {"cli_ana", "cli_bruno", "cli_carla"}
    for pedido in PEDIDOS:
        assert pedido["cliente_id"] in ids_clientes
        assert pedido["linha"] in {"notebooks", "celulares", "acessorios"}
        assert pedido["status"] in {
            "entregue",
            "em_transporte",
            "cancelado",
            "aguardando_pagamento",
            "devolvido",
        }
    for cliente in ids_clientes:
        valores = [p["valor"] for p in PEDIDOS if p["cliente_id"] == cliente]
        assert 2 <= len(valores) <= 3
        assert any(v < 300 for v in valores) and any(v > 300 for v in valores)
    for reembolso in REEMBOLSOS:
        assert reembolso["cliente_id"] == "cli_carla"
        assert any(p["id"] == reembolso["pedido_id"] for p in PEDIDOS)
