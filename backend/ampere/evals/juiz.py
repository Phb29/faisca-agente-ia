"""Juiz: três perguntas binárias com crítica, respondidas pelo modelo do papel `juiz`.

Fidelidade e relevância avaliam a geração do RAG; resolução avalia a resposta final do
agente. O juiz é deliberadamente outro modelo que o gerador (ver docs/adr/0002), para não
avaliar a própria escrita. Cada função devolve um `Veredito` via saída estruturada.
"""

from collections.abc import Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from ampere.prompts import carregar_prompt


class Veredito(BaseModel):
    aprovada: bool
    critica: str


class Exemplo(BaseModel):
    """Um par rotulado por humano, usado como few-shot no prompt de resolução."""

    mensagem: str
    resposta: str
    rotulo: bool
    critica: str


def formatar_few_shot(exemplos: Sequence[Exemplo]) -> str:
    blocos = [
        "\n".join(
            [
                f"Mensagem: {exemplo.mensagem}",
                f"Resposta: {exemplo.resposta}",
                f"Rótulo: {'Aprovada' if exemplo.rotulo else 'Reprovada'}",
                f"Crítica: {exemplo.critica}",
            ]
        )
        for exemplo in exemplos
    ]
    return "\n\n".join(blocos) or "(nenhum exemplo)"


def _julgar(juiz: BaseChatModel, nome: str, humano: str, **variaveis: str) -> Veredito:
    prompt = carregar_prompt(nome)
    resposta = juiz.with_structured_output(Veredito).invoke(
        [SystemMessage(prompt.renderizar(**variaveis)), HumanMessage(humano)],
        config={"metadata": prompt.metadata()},
    )
    return resposta if isinstance(resposta, Veredito) else Veredito.model_validate(resposta)


def julgar_fidelidade(
    juiz: BaseChatModel, *, pergunta: str, contexto: Sequence[str], resposta: str
) -> Veredito:
    """A resposta se sustenta nos trechos recuperados?"""
    trechos = "\n\n".join(f"- {trecho}" for trecho in contexto) or "(nenhum trecho)"
    humano = (
        f"Pergunta do Cliente:\n{pergunta}\n\n"
        f"Trechos da Base de Conhecimento:\n{trechos}\n\n"
        f"Resposta do chatbot:\n{resposta}"
    )
    return _julgar(juiz, "juiz_fidelidade", humano)


def julgar_relevancia(juiz: BaseChatModel, *, pergunta: str, resposta: str) -> Veredito:
    """A resposta trata do que o Cliente perguntou?"""
    humano = f"Pergunta do Cliente:\n{pergunta}\n\nResposta do chatbot:\n{resposta}"
    return _julgar(juiz, "juiz_relevancia", humano)


def julgar_resolucao(
    juiz: BaseChatModel,
    *,
    mensagem: str,
    resposta: str,
    few_shot: Sequence[Exemplo] = (),
) -> Veredito:
    """A resposta resolve o problema sem prometer nada fora da política?"""
    humano = f"Mensagem do Cliente:\n{mensagem}\n\nResposta do chatbot:\n{resposta}"
    return _julgar(juiz, "juiz_resolucao", humano, few_shot=formatar_few_shot(few_shot))
