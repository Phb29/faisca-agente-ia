"""Langfuse Cloud: cada Conversa é uma sessão, cada chamada ao Jev é um span com probabilidades.

Sem chaves configuradas, tudo aqui é no-op, para o sistema (e os testes) rodarem sem Langfuse.
"""

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Any

from ampere.nucleo.config import Config
from ampere.nucleo.jev import EstadoDoJev, RespostasJev


class Observabilidade:
    def __init__(self, config: Config, *, cliente: Any | None = None) -> None:
        self.config = config
        self._cliente = cliente
        if cliente is None and config.langfuse_public_key and config.langfuse_secret_key:
            from langfuse import Langfuse

            self._cliente = Langfuse(
                public_key=config.langfuse_public_key,
                secret_key=config.langfuse_secret_key,
                base_url=config.langfuse_base_url,
            )

    @property
    def ativa(self) -> bool:
        return self._cliente is not None

    @property
    def cliente(self) -> Any | None:
        """O cliente do Langfuse (datasets e runs dos evals), ou None sem chaves."""
        return self._cliente

    def callback(self) -> Any | None:
        """CallbackHandler oficial do LangChain, para passar no invoke do grafo."""
        if not self.ativa:
            return None
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()

    @contextmanager
    def contexto_da_conversa(
        self,
        conversa_id: str,
        cliente_id: str,
        *,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[None]:
        """session_id = thread da Conversa, user_id = Cliente, em todos os spans dentro."""
        if not self.ativa:
            yield
            return
        from langfuse import propagate_attributes

        with propagate_attributes(
            session_id=conversa_id, user_id=cliente_id, tags=tags, metadata=metadata
        ):
            yield

    def registrar_jev(
        self,
        nome: str,
        estado: EstadoDoJev,
        respostas: RespostasJev,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Span manual por chamada ao Jev, com as probabilidades e a confiança como metadata."""
        if not self.ativa:
            return
        meta = {
            "probabilidades": respostas.probabilidades(),
            "confianca": {n: r.confianca for n, r in respostas.choices.items()},
            **(metadata or {}),
        }
        saida = {
            **{n: r.probabilidade for n, r in respostas.nouls.items()},
            **{n: r.escolha for n, r in respostas.choices.items()},
        }
        with self._cliente.start_as_current_observation(
            name=f"jev.{nome}", as_type="guardrail", input=estado, output=saida, metadata=meta
        ):
            pass

    def marcar(self, *, tags: list[str] | None = None, metadata: dict[str, Any] | None = None):
        """Tags do trace (intenção do Roteador, motivo de bloqueio) e metadata (prompt)."""
        if not self.ativa:
            return nullcontext()
        from langfuse import propagate_attributes

        return propagate_attributes(tags=tags, metadata=metadata)

    def encerrar(self) -> None:
        if self.ativa and hasattr(self._cliente, "flush"):
            self._cliente.flush()
