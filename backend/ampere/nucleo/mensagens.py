"""Leitura das mensagens de uma Conversa: o turno atual, a última fala de cada lado e o
formato de texto que os prompts do trabalhador recebem."""

from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage


def ultima_do_cliente(messages: Sequence[BaseMessage]) -> HumanMessage | None:
    return next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)


def texto_da_ultima_do_cliente(messages: Sequence[BaseMessage]) -> str:
    mensagem = ultima_do_cliente(messages)
    return str(mensagem.content) if mensagem else ""


def ultima_resposta_do_assistente(messages: Sequence[BaseMessage]) -> str:
    """A última fala do assistente com texto (tool calls sem texto não contam)."""
    for mensagem in reversed(messages):
        if isinstance(mensagem, AIMessage) and mensagem.content:
            return str(mensagem.content)
    return ""


def mensagens_do_turno(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Tudo o que veio depois da última mensagem do Cliente."""
    for posicao in range(len(messages) - 1, -1, -1):
        if isinstance(messages[posicao], HumanMessage):
            return list(messages[posicao + 1 :])
    return list(messages)


def resultados_das_acoes(messages: Sequence[BaseMessage]) -> list[str]:
    """O que cada Ação devolveu neste turno, como `nome: resultado`."""
    return [
        f"{m.name}: {m.content}" for m in mensagens_do_turno(messages) if isinstance(m, ToolMessage)
    ]


def formatar_conversa(messages: Sequence[BaseMessage], *, com_acoes: bool = False) -> str:
    """Uma linha por fala ("Cliente: ...", "Assistente: ..."); `com_acoes` inclui as Ações."""
    linhas = []
    for mensagem in messages:
        if isinstance(mensagem, HumanMessage):
            linhas.append(f"Cliente: {mensagem.content}")
        elif isinstance(mensagem, AIMessage) and mensagem.content:
            linhas.append(f"Assistente: {mensagem.content}")
        elif com_acoes and isinstance(mensagem, ToolMessage):
            linhas.append(f"Ação {mensagem.name}: {mensagem.content}")
    return "\n".join(linhas)
