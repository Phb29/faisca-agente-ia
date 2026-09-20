"""Gate de Aprovação do Reembolso: o Jev decide se a operação exige um Atendente.

Duas regras por código vêm antes do Jev, porque são política da Loja e não julgamento:
valor acima do limite e Reembolso recente sempre exigem aprovação. Abaixo disso, o Jev
recebe o valor e o histórico e devolve a probabilidade de a operação ser crítica.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from typesafe_sdk import Noul

from ampere.nucleo.jev import ClienteJev

Motivo = Literal["valor_acima_do_limite", "reembolso_recente", "gate"]


@dataclass(frozen=True)
class DecisaoDoGate:
    exige_aprovacao: bool
    probabilidade: float
    motivo: Motivo


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
    limiar: float,
) -> DecisaoDoGate:
    if float(valor) > valor_limite:
        return DecisaoDoGate(True, 1.0, "valor_acima_do_limite")
    if reembolsos_recentes > 0:
        return DecisaoDoGate(True, 1.0, "reembolso_recente")
    estado = {
        "valor": float(valor),
        "valor_limite_para_aprovacao_automatica": valor_limite,
        "reembolsos_nos_ultimos_30_dias": reembolsos_recentes,
    }
    resposta = jev.perguntar(estado, {"exige_aprovacao": PERGUNTA})
    probabilidade = resposta.nouls["exige_aprovacao"].probabilidade
    return DecisaoDoGate(probabilidade >= limiar, probabilidade, "gate")
