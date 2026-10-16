"""Os três goldens como a aba Dados da Tela de Avaliação os mostra: o arquivo, o total, a
contagem por grupo e as linhas, lidos dos mesmos CSVs e pelas mesmas funções que o eval usa.

Ids e grupos são os das execuções (`rag-000`, `ag01`, `rot-00`), para uma linha da aba e um
caso de uma execução se reconhecerem. No juiz, cada linha diz em que conjunto cai, pela mesma
divisão que a calibração e a amostra ao vivo usam.
"""

from collections import Counter
from typing import Any

from ampere.evals import agente, calibracao, rag


def _busca() -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    linhas = [
        {
            "id": rag.id_da_pergunta(i),
            "grupo": linha.origem,
            "pergunta": linha.pergunta,
            "documento_esperado": linha.documento_esperado,
            "resposta_referencia": linha.resposta_referencia,
        }
        for i, linha in enumerate(rag.carregar_golden_rag())
    ]
    return "golden_rag.csv", linhas, {}


def _agente() -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    linhas = [
        {
            "id": cenario.id,
            "grupo": agente.grupo_do_cenario(cenario),
            "mensagem": cenario.mensagem,
            "cliente_id": cenario.cliente_id,
            "pedido_id": cenario.pedido_id,
            "memorias": cenario.memorias,
            "intencao_esperada": cenario.intencao_esperada,
            "acao_esperada": cenario.acao_esperada,
            "desfecho_esperado": cenario.desfecho_esperado,
            "guardrail_bloqueia": cenario.guardrail_bloqueia,
        }
        for cenario in agente.carregar_golden_agente()
    ]
    return "golden_agente.csv", linhas, {}


def _juiz() -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    rotulos = calibracao.carregar_rotulos()
    divisao = calibracao.dividir(rotulos, seed=calibracao.SEED_DA_AMOSTRA)
    conjunto_de = {
        r.indice: nome for nome in ("treino", "dev", "teste") for r in getattr(divisao, nome)
    }
    linhas = [
        {
            "id": calibracao.id_do_rotulo(r),
            "grupo": "aprovada" if r.aprovada else "reprovada",
            "conjunto": conjunto_de[r.indice],
            "mensagem": r.mensagem,
            "resposta": r.resposta,
            "aprovada": r.aprovada,
            "critica": r.critica,
        }
        for r in rotulos
    ]
    extra = {
        "conjuntos": {
            "treino": len(divisao.treino),
            "dev": len(divisao.dev),
            "teste": len(divisao.teste),
        }
    }
    return "rotulos_humanos.csv", linhas, extra


_MONTADORES = {"rag": _busca, "agente": _agente, "juiz": _juiz}


def conjunto_de_dados(eval: str) -> dict[str, Any]:
    """O golden do eval (`rag`, `agente` ou `juiz`); ValueError para qualquer outro nome."""
    if eval not in _MONTADORES:
        raise ValueError(f"eval desconhecido: {eval!r}")
    arquivo, linhas, extra = _MONTADORES[eval]()
    return {
        "eval": eval,
        "arquivo": arquivo,
        "n": len(linhas),
        "grupos": dict(Counter(linha["grupo"] for linha in linhas)),
        **extra,
        "linhas": linhas,
    }
