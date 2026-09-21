"""Gate de Aprovação do Reembolso: o Jev decide se a operação exige um Atendente.

O Jev recebe o valor, o limite da Loja para aprovação automática e o histórico recente do
Cliente, e devolve a probabilidade de a operação ser crítica. Duas regras de política vêm
por cima, configuráveis: valor acima do limite e Reembolso recente sempre exigem aprovação,
qualquer que seja a probabilidade. O motivo diz qual das três coisas decidiu.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from typesafe_sdk import Noul

from ampere.nucleo.jev import ClienteJev, RespostasJev

Motivo = Literal["valor_acima_do_limite", "reembolso_recente", "gate", "automatico"]


@dataclass(frozen=True)
class DecisaoDoGate:
    exige_aprovacao: bool
    probabilidade: float
    motivo: Motivo
    respostas: RespostasJev


PERGUNTA = Noul(
    instructions=(
        "Considerando o valor do Reembolso pedido, o valor limite da Loja para aprovação "
        "automática e o histórico recente do Cliente, esta operação é crítica o bastante para "
        "exigir a aprovação de um Atendente humano antes de ser executada?"
    ),
    criteria={
        "true": (
            "O valor é alto em relação ao limite, ou o padrão sugere risco de fraude ou abuso, "
            "ou há algo incomum que um humano deveria olhar."
        ),
        "false": (
            "É um Reembolso pequeno e rotineiro, sem sinal de risco, que pode ser feito "
            "automaticamente."
        ),
    },
)


def avaliar_gate(
    jev: ClienteJev,
    *,
    valor: Decimal,
    valor_limite: float,
    reembolsos_recentes: int,
    janela_dias: int,
    limiar: float,
) -> DecisaoDoGate:
    acima_do_limite = float(valor) > valor_limite
    estado = {
        "valor": float(valor),
        "valor_limite_para_aprovacao_automatica": valor_limite,
        "valor_acima_do_limite": acima_do_limite,
        f"reembolsos_nos_ultimos_{janela_dias}_dias": reembolsos_recentes,
    }
    respostas = jev.perguntar(estado, {"exige_aprovacao": PERGUNTA})
    probabilidade = respostas.nouls["exige_aprovacao"].probabilidade
    if acima_do_limite:
        return DecisaoDoGate(True, probabilidade, "valor_acima_do_limite", respostas)
    if reembolsos_recentes > 0:
        return DecisaoDoGate(True, probabilidade, "reembolso_recente", respostas)
    if probabilidade >= limiar:
        return DecisaoDoGate(True, probabilidade, "gate", respostas)
    return DecisaoDoGate(False, probabilidade, "automatico", respostas)
