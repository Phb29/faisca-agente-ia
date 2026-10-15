"""Guardrail de entrada: uma chamada ao Jev com as perguntas de regras/guardrail_entrada.yaml.

Cada regra tem um efeito. As de `bloquear` encerram o turno com a resposta fixa da regra (a
primeira que disparar, na ordem do arquivo). As de `marcar_como_sensivel` deixam a Conversa
seguir, mas impedem que fatos do turno virem memória de longo prazo.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import model_validator

from ampere.nucleo.jev import ClienteJev, RespostasJev
from ampere.regras import PerguntaSimNao, Regras, carregar_regras

CONTEXTO_DA_LOJA = (
    "chatbot de suporte de um e-commerce de eletrônicos (notebooks, celulares, acessórios): "
    "dúvidas de política, pedidos, reembolsos, tickets"
)


class RegraDeEntrada(PerguntaSimNao):
    efeito: Literal["bloquear", "marcar_como_sensivel"]
    resposta: str | None = None

    @model_validator(mode="after")
    def _bloqueio_precisa_de_resposta(self) -> "RegraDeEntrada":
        if self.efeito == "bloquear" and not self.resposta:
            raise ValueError("regra de bloqueio sem `resposta` para o Cliente")
        return self


REGRAS = carregar_regras("guardrail_entrada", Regras[RegraDeEntrada])
RESPOSTAS_FIXAS: dict[str, str] = {
    nome: regra.resposta
    for nome, regra in REGRAS.regras.items()
    if regra.efeito == "bloquear" and regra.resposta
}


@dataclass(frozen=True)
class ResultadoEntrada:
    bloqueio: str | None
    resposta_fixa: str | None
    sensivel: bool
    probabilidades: dict[str, float]
    respostas: RespostasJev


def avaliar_entrada(
    jev: ClienteJev,
    mensagem: str,
    *,
    limiar: float,
    limiar_sensivel: float = 0.5,
    ultima_resposta: str = "",
    regras: Regras[RegraDeEntrada] = REGRAS,
) -> ResultadoEntrada:
    """Uma chamada ao Jev; `>=` no limiar dispara a regra."""
    estado = {
        "mensagem_do_cliente": mensagem,
        "ultima_resposta_do_chatbot": ultima_resposta or "(início da Conversa)",
        "contexto": CONTEXTO_DA_LOJA,
    }
    respostas = jev.perguntar(estado, regras.perguntas())
    probabilidades = {nome: respostas.nouls[nome].probabilidade for nome in regras.regras}

    def disparou(nome: str, regra: RegraDeEntrada) -> bool:
        corte = limiar if regra.efeito == "bloquear" else limiar_sensivel
        return probabilidades[nome] >= corte

    disparadas = {nome: r for nome, r in regras.regras.items() if disparou(nome, r)}
    bloqueio = next((nome for nome, r in disparadas.items() if r.efeito == "bloquear"), None)
    return ResultadoEntrada(
        bloqueio=bloqueio,
        resposta_fixa=regras.regras[bloqueio].resposta if bloqueio else None,
        sensivel=any(r.efeito == "marcar_como_sensivel" for r in disparadas.values()),
        probabilidades=probabilidades,
        respostas=respostas,
    )
