"""Extrai fatos e um episódio da Conversa com o trabalhador e grava no Store do Cliente."""

from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.store.base import BaseStore
from pydantic import BaseModel, Field

from ampere.grafo.prompts import carregar_prompt
from ampere.memoria.carregar import CHAVE_PROCEDURAL, ler_procedural
from ampere.memoria.store import namespace_episodica, namespace_procedural, namespace_semantica

__all__ = [
    "MemoriasExtraidas",
    "escrever_procedural",
    "formatar_conversa",
    "ler_procedural",
    "salvar_memorias",
]


class MemoriasExtraidas(BaseModel):
    fatos: list[str] = Field(default_factory=list)
    episodio: str


def formatar_conversa(messages: list[BaseMessage]) -> str:
    """'Cliente: ...' / 'Assistente: ...'; ignora mensagens de tool, de sistema e vazias."""
    linhas = []
    for mensagem in messages:
        conteudo = mensagem.content if isinstance(mensagem.content, str) else str(mensagem.content)
        if not conteudo.strip():
            continue
        if isinstance(mensagem, HumanMessage):
            linhas.append(f"Cliente: {conteudo.strip()}")
        elif isinstance(mensagem, AIMessage):
            linhas.append(f"Assistente: {conteudo.strip()}")
    return "\n".join(linhas)


def salvar_memorias(
    store: BaseStore,
    trabalhador: BaseChatModel,
    cliente_id: str,
    messages: list[BaseMessage],
    *,
    desfecho: str,
    acoes: list[str],
    fatos_conhecidos: list[str] | None = None,
) -> MemoriasExtraidas:
    """Renderiza o prompt `extrair_memorias`, chama o trabalhador e grava fatos e episódio."""
    prompt = carregar_prompt("extrair_memorias")
    conhecidos = "\n".join(f"- {fato}" for fato in fatos_conhecidos or []) or "(nenhum)"
    system = prompt.renderizar(fatos_conhecidos=conhecidos, conversa=formatar_conversa(messages))
    extraidas: MemoriasExtraidas = trabalhador.with_structured_output(MemoriasExtraidas).invoke(
        [SystemMessage(system), HumanMessage("Extraia as memórias.")]
    )

    for fato in extraidas.fatos:
        store.put(namespace_semantica(cliente_id), str(uuid4()), {"texto": fato})
    store.put(
        namespace_episodica(cliente_id),
        str(uuid4()),
        {
            "resumo": extraidas.episodio,
            "desfecho": desfecho,
            "acoes": list(acoes),
            "data": datetime.now(UTC).isoformat(),
        },
        index=False,
    )
    return extraidas


def escrever_procedural(store: BaseStore, cliente_id: str, texto: str) -> None:
    store.put(namespace_procedural(cliente_id), CHAVE_PROCEDURAL, {"texto": texto}, index=False)
