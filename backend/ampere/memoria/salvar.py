"""Ao fim de cada turno, o trabalhador extrai fatos, um episódio e, quando o Cliente pediu,
as preferências dele sobre a forma de falar. Tudo é gravado no Store do Cliente."""

from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.store.base import BaseStore
from pydantic import BaseModel, Field

from ampere.memoria.procedural import escrever_preferencias
from ampere.memoria.store import namespace_episodica, namespace_semantica
from ampere.nucleo.mensagens import formatar_conversa, texto_da_ultima_do_cliente
from ampere.prompts import carregar_prompt


class MemoriasExtraidas(BaseModel):
    fatos: list[str] = Field(default_factory=list)
    episodio: str
    # None quer dizer "não mexer"; uma lista, mesmo vazia, substitui a anterior.
    preferencias: list[str] | None = None


def _em_lista(itens: list[str] | None, vazio: str) -> str:
    return "\n".join(f"- {item}" for item in itens or []) or vazio


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
    preferencias_atuais: list[str] | None = None,
    guardar_preferencias: bool = False,
) -> MemoriasExtraidas:
    """Grava o episódio sempre, os fatos só com `guardar_fatos` (turno sem dado sensível) e
    as preferências só com `guardar_preferencias` (turno sem bloqueio e sem dado sensível).
    Na dúvida, não grava: por isso `guardar_preferencias` começa falso."""
    prompt = carregar_prompt("extrair_memorias")
    sistema = prompt.renderizar(
        preferencias_atuais=_em_lista(preferencias_atuais, "(nenhuma)"),
        ultima_mensagem_do_cliente=texto_da_ultima_do_cliente(messages) or "(nenhuma)",
        fatos_conhecidos=_em_lista(fatos_conhecidos, "(nenhum)"),
        conversa=formatar_conversa(messages),
    )
    extraidas: MemoriasExtraidas = trabalhador.with_structured_output(MemoriasExtraidas).invoke(
        [SystemMessage(sistema), HumanMessage("Extraia as memórias.")],
        config={"metadata": prompt.metadata()},
    )

    if guardar_fatos:
        for fato in extraidas.fatos:
            store.put(namespace_semantica(cliente_id), str(uuid4()), {"texto": fato})
    if guardar_preferencias and extraidas.preferencias is not None:
        escrever_preferencias(store, cliente_id, extraidas.preferencias)
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
