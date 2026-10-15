"""Gate de Aprovação do Reembolso (as regras, em texto, estão em regras/gate_de_aprovacao.yaml).

Dois tipos de Pedido nem chegam ao Gate: o que ainda aguarda pagamento e o que já foi
reembolsado. Para os demais, valor acima do limite e Reembolso recente exigem aprovação por
código, e só depois disso a probabilidade do Jev decide. O motivo diz qual das três coisas
decidiu, e vai para o cartão da Aprovação Pendente.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, TypedDict

from ampere.loja.pedidos import STATUS_SEM_PAGAMENTO, Pedido, StoreDePedidos
from ampere.nucleo.jev import ClienteJev, RespostasJev
from ampere.regras import PerguntaSimNao, Regras, carregar_regras

REGRAS = carregar_regras("gate_de_aprovacao", Regras[PerguntaSimNao])

Motivo = Literal["valor_acima_do_limite", "reembolso_recente", "gate", "automatico"]


class DecisaoGravada(TypedDict):
    """A decisão como fica no estado do grafo, para a retomada não perguntar de novo."""

    exige_aprovacao: bool
    probabilidade: float
    motivo: Motivo


@dataclass(frozen=True)
class DecisaoDoGate:
    exige_aprovacao: bool
    probabilidade: float
    motivo: Motivo
    respostas: RespostasJev

    def para_o_estado(self) -> DecisaoGravada:
        return {
            "exige_aprovacao": self.exige_aprovacao,
            "probabilidade": self.probabilidade,
            "motivo": self.motivo,
        }


def motivo_para_recusar(pedido: Pedido, pedidos: StoreDePedidos) -> str | None:
    """Por que este Pedido não pode ser reembolsado, ou None se pode."""
    if pedido.status == STATUS_SEM_PAGAMENTO:
        return "o pagamento deste Pedido ainda não foi confirmado"
    if pedidos.reembolso_do_pedido(pedido.cliente_id, pedido.id) is not None:
        return "este Pedido já foi reembolsado"
    return None


def avaliar_gate(
    jev: ClienteJev,
    *,
    valor: Decimal,
    valor_limite: float,
    reembolsos_recentes: int,
    janela_dias: int,
    limiar: float,
) -> DecisaoDoGate:
    """Uma chamada ao Jev e as duas regras de política por cima."""
    acima_do_limite = float(valor) > valor_limite
    estado = {
        "valor": float(valor),
        "valor_limite_para_aprovacao_automatica": valor_limite,
        "valor_acima_do_limite": acima_do_limite,
        f"reembolsos_nos_ultimos_{janela_dias}_dias": reembolsos_recentes,
    }
    respostas = jev.perguntar(estado, REGRAS.perguntas())
    probabilidade = respostas.nouls["exige_aprovacao"].probabilidade
    if acima_do_limite:
        motivo: Motivo = "valor_acima_do_limite"
    elif reembolsos_recentes > 0:
        motivo = "reembolso_recente"
    elif probabilidade >= limiar:
        motivo = "gate"
    else:
        motivo = "automatico"
    return DecisaoDoGate(motivo != "automatico", probabilidade, motivo, respostas)
