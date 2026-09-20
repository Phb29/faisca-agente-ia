"""Quem executa um job. O worker só conhece este Protocol; o executor real, que roda o
grafo (`ExecutorDoGrafo`), vive neste mesmo arquivo mas é escrito junto com o grafo.

Convenção dos dados de cada evento:
- token: {"texto"}
- tool_call: {"nome", "args"}
- approval_required: {"pedido_id", "valor", "probabilidade", "resumo"}
- message_done: {"mensagem_id", "conteudo"}
- error: {"mensagem"}
"""

from collections.abc import Callable, Iterator
from typing import Protocol

from ampere.fila.eventos import Evento
from ampere.fila.fila import Job


class Executor(Protocol):
    def executar(self, job: Job) -> Iterator[Evento]: ...


class ExecutorFalso:
    """Emite uma lista fixa de eventos, ou a lista que uma função devolve para o job.
    Guarda em `self.jobs` os jobs recebidos, para asserções."""

    def __init__(self, eventos: list[Evento] | Callable[[Job], list[Evento]]):
        self._eventos = eventos
        self.jobs: list[Job] = []

    def executar(self, job: Job) -> Iterator[Evento]:
        self.jobs.append(job)
        eventos = self._eventos(job) if callable(self._eventos) else self._eventos
        yield from eventos


class ExecutorDoGrafo:
    """Roda o grafo com streaming e traduz o que sai nos cinco eventos da fila.

    `messages` vira `token` (só o texto do gerador e do agente), `custom` vira `tool_call`,
    `__interrupt__` vira `approval_required` e o fim do turno vira `message_done`. Uma
    exceção sobe para o worker, que grava o erro no job e publica `error`.
    """

    NOS_QUE_ESCREVEM = ("gerar_resposta", "agente")

    def __init__(self, grafo, *, observabilidade=None) -> None:
        self.grafo = grafo
        self.observabilidade = observabilidade

    @staticmethod
    def entrada_do_job(job: Job):
        from langchain_core.messages import HumanMessage
        from langgraph.types import Command

        if job.tipo == "retomada":
            return Command(
                resume={
                    "aprovado": bool(job.payload.get("aprovado")),
                    "motivo": job.payload.get("motivo"),
                }
            )
        return {
            "messages": [HumanMessage(job.payload["conteudo"])],
            "cliente_id": job.payload.get("cliente_id", ""),
            "conversa_id": job.conversa_id,
        }

    def executar(self, job: Job) -> Iterator[Evento]:
        from contextlib import ExitStack, nullcontext

        from langchain_core.messages import AIMessage, AIMessageChunk

        cliente_id = job.payload.get("cliente_id", "")
        config: dict = {"configurable": {"thread_id": job.conversa_id, "cliente_id": cliente_id}}
        obs = self.observabilidade
        callback = obs.callback() if obs else None
        if callback:
            config["callbacks"] = [callback]
        contexto = obs.contexto_da_conversa(job.conversa_id, cliente_id) if obs else nullcontext()

        interrompido = False
        with contexto, ExitStack() as marcacoes:
            fluxo = self.grafo.stream(
                self.entrada_do_job(job), config, stream_mode=["messages", "custom", "updates"]
            )
            for modo, pedaco in fluxo:
                if modo == "messages":
                    mensagem, metadata = pedaco
                    if (
                        metadata.get("langgraph_node") in self.NOS_QUE_ESCREVEM
                        and isinstance(mensagem, AIMessageChunk)
                        and mensagem.content
                        and not mensagem.tool_call_chunks
                    ):
                        yield Evento(tipo="token", dados={"texto": str(mensagem.content)})
                elif modo == "custom" and pedaco.get("tipo") == "tool_call":
                    yield Evento(
                        tipo="tool_call",
                        dados={"nome": pedaco["nome"], "args": pedaco.get("args", {})},
                    )
                elif modo == "updates":
                    for interrupcao in pedaco.get("__interrupt__", ()):
                        interrompido = True
                        valor = dict(interrupcao.value)
                        yield Evento(
                            tipo="approval_required",
                            dados={
                                "pedido_id": valor["pedido_id"],
                                "valor": valor["valor"],
                                "probabilidade": valor["probabilidade"],
                                "resumo": valor["resumo"],
                                "motivo_do_gate": valor.get("motivo_do_gate"),
                            },
                        )
                    if obs:
                        for no, atualizacao in pedaco.items():
                            tag = _tag_do_no(no, atualizacao)
                            if tag:
                                marcacoes.enter_context(obs.marcar(tags=[tag]))
        if interrompido:
            return
        estado = self.grafo.get_state(config).values
        ultima = next(
            (m for m in reversed(estado.get("messages", [])) if isinstance(m, AIMessage)), None
        )
        yield Evento(
            tipo="message_done",
            dados={
                "conteudo": str(ultima.content) if ultima else "",
                "desfecho": estado.get("desfecho"),
            },
        )


def _tag_do_no(no: str, atualizacao) -> str | None:
    if not isinstance(atualizacao, dict):
        return None
    if no == "roteador" and atualizacao.get("intencao"):
        return f"intencao:{atualizacao['intencao']}"
    if no == "guardrail_entrada" and atualizacao.get("bloqueio"):
        return f"bloqueio:{atualizacao['bloqueio']}"
    if no == "guardrail_saida" and atualizacao.get("desfecho") == "Escalada":
        return "desfecho:escalada"
    return None
