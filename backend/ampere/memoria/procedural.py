"""Memória Procedural: como atender um Cliente, lida no início de cada turno. Tem duas partes,
em duas chaves do mesmo namespace:

- as instruções do Atendente (`instrucoes`), um texto livre que só a Central escreve;
- as preferências do Cliente sobre a forma de falar (`preferencias_do_cliente`), uma lista
  curta que o fim do turno grava sozinho quando o próprio Cliente pede, e que o Atendente vê
  e apaga na Central.

As preferências vêm de texto do Cliente e entram no prompt de sistema, então são limitadas
aqui, na escrita e na leitura: aparadas, uma linha cada, sem vazias nem repetidas, com até
120 caracteres e no máximo 5, as mais recentes.
"""

from collections.abc import Iterable

from langgraph.store.base import BaseStore

from ampere.memoria.store import namespace_procedural

CHAVE = "instrucoes"
CHAVE_PREFERENCIAS = "preferencias_do_cliente"
MAXIMO_DE_PREFERENCIAS = 5
TAMANHO_DA_PREFERENCIA = 120


def ler_procedural(store: BaseStore, cliente_id: str) -> str:
    item = store.get(namespace_procedural(cliente_id), CHAVE)
    return str(item.value.get("texto", "")) if item else ""


def escrever_procedural(store: BaseStore, cliente_id: str, texto: str) -> None:
    store.put(namespace_procedural(cliente_id), CHAVE, {"texto": texto}, index=False)


def normalizar_preferencias(itens: Iterable[object]) -> list[str]:
    """A lista vai da mais antiga para a mais recente. Quebras de linha viram espaço, para
    uma preferência nunca abrir uma seção nova no prompt; repetidas contam uma vez, sem
    diferenciar maiúsculas; passando de 5, ficam as 5 mais recentes."""
    vistas: set[str] = set()
    limpas: list[str] = []
    for item in itens:
        texto = " ".join(str(item).split())[:TAMANHO_DA_PREFERENCIA].strip()
        if texto and texto.casefold() not in vistas:
            vistas.add(texto.casefold())
            limpas.append(texto)
    return limpas[-MAXIMO_DE_PREFERENCIAS:]


def ler_preferencias(store: BaseStore, cliente_id: str) -> list[str]:
    item = store.get(namespace_procedural(cliente_id), CHAVE_PREFERENCIAS)
    itens = item.value.get("itens") if item else None
    return normalizar_preferencias(itens) if isinstance(itens, list) else []


def escrever_preferencias(store: BaseStore, cliente_id: str, itens: Iterable[str]) -> None:
    """Substitui a lista inteira, já normalizada."""
    store.put(
        namespace_procedural(cliente_id),
        CHAVE_PREFERENCIAS,
        {"itens": normalizar_preferencias(itens)},
        index=False,
    )


class MemoriaProcedural:
    """O que a API usa para ler e editar a Memória Procedural, sobre o Store do LangGraph."""

    def __init__(self, store: BaseStore) -> None:
        self._store = store

    def ler(self, cliente_id: str) -> str:
        return ler_procedural(self._store, cliente_id)

    def escrever(self, cliente_id: str, texto: str) -> None:
        escrever_procedural(self._store, cliente_id, texto.strip())

    def ler_preferencias(self, cliente_id: str) -> list[str]:
        return ler_preferencias(self._store, cliente_id)

    def escrever_preferencias(self, cliente_id: str, itens: list[str]) -> None:
        escrever_preferencias(self._store, cliente_id, itens)
