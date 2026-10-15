"""Regras do Jev em YAML: todas carregam, estão completas, e acrescentar uma regra de
bloqueio é só editar o arquivo."""

import pytest
from pydantic import ValidationError

from ampere.acoes.reembolso import REGRAS as REGRAS_DO_GATE
from ampere.guardrails.entrada import REGRAS as REGRAS_DE_ENTRADA
from ampere.guardrails.entrada import RegraDeEntrada, avaliar_entrada
from ampere.guardrails.saida import REGRAS as REGRAS_DE_SAIDA
from ampere.nucleo.falsos import JevFalso
from ampere.regras import PerguntaDeEscolha, PerguntaSimNao, Regras
from ampere.roteador.roteador import REGRAS as REGRAS_DO_ROTEADOR

TODAS = [REGRAS_DE_ENTRADA, REGRAS_DE_SAIDA, REGRAS_DO_ROTEADOR, REGRAS_DO_GATE]


@pytest.mark.parametrize("regras", TODAS, ids=lambda r: r.nome)
def test_todo_arquivo_tem_nome_versao_e_perguntas_completas(regras):
    assert regras.nome and regras.versao >= 1
    for pergunta in regras.perguntas().values():
        assert pergunta.pergunta.strip()
        if isinstance(pergunta, PerguntaSimNao):
            assert pergunta.sim_quando.strip() and pergunta.nao_quando.strip()
        else:
            assert all(texto.strip() for texto in pergunta.opcoes.values())


def test_guardrails_e_gate_sao_sim_ou_nao_e_roteador_e_escolha():
    assert all(isinstance(p, PerguntaSimNao) for p in REGRAS_DE_ENTRADA.perguntas().values())
    assert all(isinstance(p, PerguntaSimNao) for p in REGRAS_DE_SAIDA.perguntas().values())
    assert all(isinstance(p, PerguntaSimNao) for p in REGRAS_DO_GATE.perguntas().values())
    assert isinstance(REGRAS_DO_ROTEADOR.perguntas()["intencao"], PerguntaDeEscolha)


def test_nomes_das_perguntas_que_o_codigo_espera():
    assert list(REGRAS_DE_ENTRADA.regras) == ["manipulacao", "fora_de_escopo", "dado_sensivel"]
    assert list(REGRAS_DE_SAIDA.regras) == ["fora_do_contexto", "promessa_indevida", "vazamento"]
    assert list(REGRAS_DO_GATE.regras) == ["exige_aprovacao"]
    assert REGRAS_DE_SAIDA.resposta_ao_escalar.strip()


def test_campo_desconhecido_no_yaml_e_erro_de_validacao():
    with pytest.raises(ValidationError):
        Regras[PerguntaSimNao].model_validate(
            {
                "nome": "x",
                "versao": 1,
                "regras": {"a": {"pergunta": "?", "sim_quando": "s", "nao_quando": "n", "b": 1}},
            }
        )


def test_regra_de_bloqueio_sem_resposta_ao_cliente_e_erro_de_validacao():
    with pytest.raises(ValidationError, match="resposta"):
        RegraDeEntrada(pergunta="?", sim_quando="s", nao_quando="n", efeito="bloquear")


def test_regra_de_bloqueio_nova_funciona_sem_mudar_codigo():
    promocao = RegraDeEntrada(
        pergunta="O Cliente pede cupom?",
        sim_quando="Pede cupom.",
        nao_quando="Não pede.",
        efeito="bloquear",
        resposta="Não temos cupons neste canal.",
    )
    regras = REGRAS_DE_ENTRADA.model_copy(
        update={"regras": {**REGRAS_DE_ENTRADA.regras, "cupom": promocao}}
    )

    resultado = avaliar_entrada(
        JevFalso(nouls={"cupom": 0.9}), "tem cupom?", limiar=0.7, regras=regras
    )

    assert resultado.bloqueio == "cupom"
    assert resultado.resposta_fixa == "Não temos cupons neste canal."
