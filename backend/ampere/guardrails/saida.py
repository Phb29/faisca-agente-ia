"""Guardrail de saída: uma chamada ao Jev com as perguntas de regras/guardrail_saida.yaml.

O Jev vê a resposta candidata junto com tudo o que a sustenta: a pergunta do Cliente, os
trechos da Base de Conhecimento e o resultado de cada Ação do turno. Se qualquer regra
atingir o limiar, a resposta é reprovada com o motivo da primeira regra (na ordem do arquivo)
e a crítica dela, que volta para o prompt de quem escreveu.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from ampere.nucleo.jev import ClienteJev, RespostasJev
from ampere.regras import PerguntaSimNao, Regras, carregar_regras


class RegraDeSaida(PerguntaSimNao):
    critica: str


class RegrasDeSaida(Regras[RegraDeSaida]):
    resposta_ao_escalar: str


REGRAS = carregar_regras("guardrail_saida", RegrasDeSaida)
CRITICAS: dict[str, str] = {nome: regra.critica for nome, regra in REGRAS.regras.items()}
RESPOSTA_ESCALADA = REGRAS.resposta_ao_escalar


@dataclass(frozen=True)
class ResultadoSaida:
    motivo: str | None
    critica: str | None
    probabilidades: dict[str, float]
    respostas: RespostasJev

    @property
    def aprovada(self) -> bool:
        return self.motivo is None


def avaliar_saida(
    jev: ClienteJev,
    resposta: str,
    *,
    pergunta: str = "",
    trechos: Sequence[str] = (),
    resultados_das_acoes: Sequence[str] = (),
    limiar: float,
    regras: RegrasDeSaida = REGRAS,
) -> ResultadoSaida:
    """Uma chamada ao Jev; reprova se qualquer regra atingir o limiar (`>=`)."""
    estado = {
        "pergunta_do_cliente": pergunta,
        "resposta_do_assistente": resposta,
        "trechos_da_base_de_conhecimento": list(trechos),
        "resultados_das_acoes": list(resultados_das_acoes),
    }
    respostas = jev.perguntar(estado, regras.perguntas())
    probabilidades = {nome: respostas.nouls[nome].probabilidade for nome in regras.regras}
    motivo = next((nome for nome, p in probabilidades.items() if p >= limiar), None)
    return ResultadoSaida(
        motivo=motivo,
        critica=regras.regras[motivo].critica if motivo else None,
        probabilidades=probabilidades,
        respostas=respostas,
    )
