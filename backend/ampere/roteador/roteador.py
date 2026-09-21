"""Roteador: uma pergunta Choice ao Jev que decide o caminho do grafo para a mensagem.

O estado leva também um resumo curto dos últimos episódios do Cliente, porque frases como
"meu último problema continua" só fazem sentido com esse histórico.
"""

from dataclasses import dataclass

from typesafe_sdk import Choice

from ampere.grafo.estado import Intencao, Memorias
from ampere.nucleo.jev import ClienteJev, RespostasJev

INTENCOES: tuple[Intencao, ...] = ("duvida", "transacao", "quer_humano")

PERGUNTA = Choice(
    instructions=(
        "Qual é a intenção da mensagem do Cliente no suporte da Ampère Eletrônicos? Use o "
        "resumo das Conversas anteriores quando a mensagem se referir a algo passado."
    ),
    criteria={
        "duvida": (
            "Quer saber uma regra ou informação da Loja: prazo de troca ou devolução, frete, "
            "garantia, formas de pagamento, cadastro, política em geral. Não pede que algo "
            "seja feito num Pedido específico."
        ),
        "transacao": (
            "Quer que algo seja feito sobre um Pedido dele: status do pedido, rastreio, "
            "reembolso, cancelamento, troca de um item comprado, problema com uma compra."
        ),
        "quer_humano": (
            "Pede explicitamente para falar com uma pessoa, atendente ou humano, ou demonstra "
            "que não quer conversar com o bot (irritação com respostas automáticas, 'quero "
            "alguém de verdade')."
        ),
    },
)


@dataclass(frozen=True)
class Roteamento:
    intencao: Intencao
    confianca: float
    probabilidades: dict[str, float]
    respostas: RespostasJev


def resumir_memorias(memorias: Memorias, *, limite: int = 3) -> str:
    """Resumo curto dos últimos episódios, em uma linha cada, para o estado do Jev."""
    linhas = []
    for episodio in memorias.get("episodica", [])[:limite]:
        resumo = episodio.get("resumo", "")
        desfecho = episodio.get("desfecho", "")
        linhas.append(f"{resumo} (desfecho: {desfecho})" if desfecho else resumo)
    return "\n".join(linhas) if linhas else "sem Conversas anteriores"


def rotear(jev: ClienteJev, mensagem: str, memorias: Memorias) -> Roteamento:
    """Uma chamada ao Jev com a Choice `intencao`."""
    estado = {
        "mensagem_do_cliente": mensagem,
        "conversas_anteriores": resumir_memorias(memorias),
    }
    respostas = jev.perguntar(estado, {"intencao": PERGUNTA})
    escolha = respostas.choices["intencao"]
    if escolha.escolha not in INTENCOES:
        raise ValueError(f"Intenção desconhecida devolvida pelo Jev: {escolha.escolha}")
    return Roteamento(
        intencao=escolha.escolha,  # type: ignore[arg-type]
        confianca=escolha.confianca,
        probabilidades=dict(escolha.probabilidades),
        respostas=respostas,
    )
