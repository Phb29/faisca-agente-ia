"""Ao fim de cada turno, o trabalhador extrai fatos e um episódio da Conversa, e os dois
são gravados no Store do Cliente."""

from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.store.base import BaseStore
from pydantic import BaseModel, Field

from ampere.memoria.store import namespace_episodica, namespace_semantica
from ampere.nucleo.mensagens import formatar_conversa
from ampere.prompts import carregar_prompt


class MemoriasExtraidas(BaseModel):
    fatos: list[str] = Field(default_factory=list)
    episodio: str


def salvar_memorias(
    store: BaseStore,
    trabalhador: BaseChatModel,
    cliente_id: str,
    messages: list[BaseMessage],
    *,
    desfecho: str,
    acoes: list[str],
    fatos_conhecidos: list[str] | None = None,
    guardar_fatos: bool = True,
) -> MemoriasExtraidas:
    """Grava o episódio sempre e os fatos só com `guardar_fatos` (turno sem dado sensível)."""
    prompt = carregar_prompt("extrair_memorias")
    conhecidos = "\n".join(f"- {fato}" for fato in fatos_conhecidos or []) or "(nenhum)"
    sistema = prompt.renderizar(fatos_conhecidos=conhecidos, conversa=formatar_conversa(messages))
    extraidas: MemoriasExtraidas = trabalhador.with_structured_output(MemoriasExtraidas).invoke(
        [SystemMessage(sistema), HumanMessage("Extraia as memórias.")],
        config={"metadata": prompt.metadata()},
    )

    if guardar_fatos:
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
