"""Observabilidade: no-op sem chaves; com cliente, cria spans do Jev com probabilidades."""

from contextlib import contextmanager

from ampere.nucleo.config import Config
from ampere.nucleo.jev import RespostaChoice, RespostaNoul, RespostasJev
from ampere.observabilidade.langfuse import Observabilidade


class ClienteEspiao:
    def __init__(self):
        self.spans = []

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        self.spans.append(kwargs)
        yield None


def test_sem_chaves_e_inativa_e_tudo_vira_no_op():
    obs = Observabilidade(Config(modelos_falsos=True))

    assert obs.ativa is False
    assert obs.callback() is None
    with obs.contexto_da_conversa("c1", "cli_ana"):
        obs.registrar_jev("roteador", {"m": "x"}, RespostasJev())
        obs.marcar(tags=["intencao:duvida"])


def test_registrar_jev_cria_span_com_probabilidades_e_confianca():
    espiao = ClienteEspiao()
    obs = Observabilidade(Config(modelos_falsos=True), cliente=espiao)
    respostas = RespostasJev(
        nouls={"manipulacao": RespostaNoul(0.1)},
        choices={"intencao": RespostaChoice("duvida", 0.9, {"duvida": 0.9, "transacao": 0.1})},
    )

    obs.registrar_jev("guardrail_entrada", {"mensagem": "oi"}, respostas, metadata={"limiar": 0.7})

    assert obs.ativa is True
    span = espiao.spans[0]
    assert span["name"] == "jev.guardrail_entrada"
    assert span["as_type"] == "guardrail"
    assert span["metadata"]["probabilidades"]["manipulacao"] == 0.1
    assert span["metadata"]["probabilidades"]["intencao.duvida"] == 0.9
    assert span["metadata"]["confianca"] == {"intencao": 0.9}
    assert span["metadata"]["limiar"] == 0.7
    assert span["input"] == {"mensagem": "oi"}
