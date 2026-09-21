"""Formatação de uma Conversa em texto, para os prompts do trabalhador e do resumo."""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage


def formatar_conversa(messages: list[BaseMessage], *, com_acoes: bool = False) -> str:
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
