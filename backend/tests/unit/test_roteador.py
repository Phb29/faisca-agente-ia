"""Roteador: uma pergunta de escolha ao Jev com três intenções."""

from ampere.nucleo.falsos import JevFalso
from ampere.regras import PerguntaDeEscolha
from ampere.roteador.roteador import rotear


def test_rotear_devolve_a_escolha_do_jev():
    jev = JevFalso(choices={"intencao": "transacao"})

    roteamento = rotear(jev, "cadê meu pedido?")

    assert roteamento.intencao == "transacao"
    assert roteamento.confianca == 1.0
    assert roteamento.probabilidades == {"duvida": 0.0, "transacao": 1.0, "quer_humano": 0.0}


def test_rotear_faz_uma_chamada_com_uma_escolha_de_tres_opcoes():
    jev = JevFalso(choices={"intencao": "quer_humano"})

    rotear(jev, "quero falar com uma pessoa")

    assert len(jev.chamadas) == 1
    estado, perguntas = jev.chamadas[0]
    assert set(perguntas) == {"intencao"}
    assert isinstance(perguntas["intencao"], PerguntaDeEscolha)
    assert list(perguntas["intencao"].opcoes) == ["duvida", "transacao", "quer_humano"]
    assert estado["mensagem_do_cliente"] == "quero falar com uma pessoa"


def test_rotear_inclui_resumo_das_memorias_no_estado():
    jev = JevFalso()
    episodios = [
        {"resumo": "Reclamou do frete atrasado", "desfecho": "Escalada", "acoes": [], "data": "d"}
    ]

    rotear(jev, "continua", episodios=episodios, ultima_resposta="Posso ajudar em algo mais?")

    estado, _ = jev.chamadas[0]
    assert estado["conversas_anteriores"] == "Reclamou do frete atrasado (desfecho: Escalada)"
    assert estado["ultima_resposta_do_chatbot"] == "Posso ajudar em algo mais?"


def test_rotear_padrao_e_duvida():
    assert rotear(JevFalso(), "qual o prazo de troca?").intencao == "duvida"
