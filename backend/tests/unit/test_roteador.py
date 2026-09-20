"""Roteador: uma Choice ao Jev com três intenções."""

from typesafe_sdk import Choice

from ampere.grafo.estado import memorias_vazias
from ampere.nucleo.falsos import JevFalso
from ampere.roteador.roteador import rotear


def test_rotear_devolve_a_escolha_do_jev():
    jev = JevFalso(choices={"intencao": "transacao"})

    roteamento = rotear(jev, "cadê meu pedido?", memorias_vazias())

    assert roteamento.intencao == "transacao"
    assert roteamento.confianca == 1.0
    assert roteamento.probabilidades == {"duvida": 0.0, "transacao": 1.0, "quer_humano": 0.0}


def test_rotear_faz_uma_chamada_com_uma_choice_de_tres_criterios():
    jev = JevFalso(choices={"intencao": "quer_humano"})

    rotear(jev, "quero falar com uma pessoa", memorias_vazias())

    assert len(jev.chamadas) == 1
    estado, perguntas = jev.chamadas[0]
    assert set(perguntas) == {"intencao"}
    assert isinstance(perguntas["intencao"], Choice)
    assert list(perguntas["intencao"].criteria) == ["duvida", "transacao", "quer_humano"]
    assert estado["mensagem_do_cliente"] == "quero falar com uma pessoa"


def test_rotear_inclui_resumo_das_memorias_no_estado():
    jev = JevFalso()
    memorias = memorias_vazias()
    memorias["episodica"] = [
        {"resumo": "Reclamou do frete atrasado", "desfecho": "Escalada", "acoes": [], "data": "d"}
    ]

    rotear(jev, "meu último problema continua", memorias)

    estado, _ = jev.chamadas[0]
    assert "Reclamou do frete atrasado" in str(estado)


def test_rotear_padrao_e_duvida():
    assert rotear(JevFalso(), "qual o prazo de troca?", memorias_vazias()).intencao == "duvida"
