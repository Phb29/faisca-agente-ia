"""Roteador: uma Choice ao Jev (regras/roteador.yaml) que decide o caminho do grafo.

O Jev recebe a mensagem, a última resposta do chatbot (sem ela, "sim, pode fazer" não tem
intenção) e um resumo dos últimos episódios do Cliente (sem ele, "meu último problema
continua" também não).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast, get_args

from ampere.nucleo.jev import ClienteJev, RespostasJev
from ampere.regras import PerguntaDeEscolha, Regras, carregar_regras

Intencao = Literal["duvida", "transacao", "quer_humano"]
INTENCOES: tuple[Intencao, ...] = get_args(Intencao)

REGRAS = carregar_regras("roteador", Regras[PerguntaDeEscolha])
if tuple(REGRAS.regras["intencao"].opcoes) != INTENCOES:
    raise ValueError(f"regras/roteador.yaml precisa das opções {INTENCOES}, nesta ordem")


@dataclass(frozen=True)
class Roteamento:
    intencao: Intencao
    confianca: float
    probabilidades: dict[str, float]
    respostas: RespostasJev


def resumir_episodios(episodios: Sequence[Mapping[str, Any]], *, limite: int = 3) -> str:
    """Um episódio por linha, com o desfecho, para o estado do Jev."""
    linhas = []
    for episodio in episodios[:limite]:
        resumo, desfecho = episodio.get("resumo", ""), episodio.get("desfecho", "")
        linhas.append(f"{resumo} (desfecho: {desfecho})" if desfecho else resumo)
    return "\n".join(linhas) or "sem Conversas anteriores"


def rotear(
    jev: ClienteJev,
    mensagem: str,
    *,
    episodios: Sequence[Mapping[str, Any]] = (),
    ultima_resposta: str = "",
) -> Roteamento:
    estado = {
        "mensagem_do_cliente": mensagem,
        "ultima_resposta_do_chatbot": ultima_resposta or "(início da Conversa)",
        "conversas_anteriores": resumir_episodios(episodios),
    }
    escolha = jev.perguntar(estado, REGRAS.perguntas())
    intencao = escolha.choices["intencao"]
    if intencao.escolha not in INTENCOES:
        raise ValueError(f"Intenção desconhecida devolvida pelo Jev: {intencao.escolha}")
    return Roteamento(
        intencao=cast(Intencao, intencao.escolha),
        confianca=intencao.confianca,
        probabilidades=dict(intencao.probabilidades),
        respostas=escolha,
    )
