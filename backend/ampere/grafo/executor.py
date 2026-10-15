"""Roda o grafo para um job da fila e traduz o que sai nos eventos do stream.

`messages` vira `token` (só o texto escrito pelo gerador e pelo agente), `custom` vira
`tool_call`, `updates` vira uma `etapa` por nó (os bastidores do turno) e, quando o Gate
interrompe, `approval_required`. O fim do turno vira `message_done`. Uma exceção sobe para o
worker, que marca o job com erro e publica `error`.

Streaming e Guardrail de saída puxam para lados opostos: o texto nasce antes de ser julgado.
Com `tokens_antes_do_guardrail`, o Cliente vê a resposta sendo escrita, e o front apaga o
rascunho se ela for reprovada; sem ele, os tokens esperam a aprovação e saem de uma vez, e
nenhum texto reprovado chega ao navegador.
"""

from collections.abc import Iterator
from contextlib import ExitStack, nullcontext
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, Interrupt

from ampere.fila.eventos import Evento
from ampere.fila.fila import Job
from ampere.observabilidade.langfuse import Observabilidade

NOS_QUE_ESCREVEM = frozenset({"gerar_resposta", "agente"})


class ExecutorDoGrafo:
    def __init__(
        self,
        grafo: CompiledStateGraph,
        *,
        observabilidade: Observabilidade | None = None,
        tokens_antes_do_guardrail: bool = True,
    ) -> None:
        self.grafo = grafo
        self.observabilidade = observabilidade
        self.tokens_antes_do_guardrail = tokens_antes_do_guardrail

    @staticmethod
    def entrada_do_job(job: Job) -> dict | Command:
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
        cliente_id = job.payload.get("cliente_id", "")
        config = self._config(job.conversa_id, cliente_id)
        obs = self.observabilidade
        contexto = obs.contexto_da_conversa(job.conversa_id, cliente_id) if obs else nullcontext()

        interrompido = False
        rascunho: list[Evento] = []
        with contexto, ExitStack() as tags:
            fluxo = self.grafo.stream(
                self.entrada_do_job(job), config, stream_mode=["messages", "custom", "updates"]
            )
            for modo, pedaco in fluxo:
                if modo == "messages":
                    if token := _token(*pedaco):
                        if self.tokens_antes_do_guardrail:
                            yield token
                        else:
                            rascunho.append(token)
                elif modo == "custom" and pedaco.get("tipo") == "tool_call":
                    yield Evento(
                        tipo="tool_call",
                        dados={"nome": pedaco["nome"], "args": pedaco.get("args", {})},
                    )
                elif modo == "updates":
                    for no, atualizacao in pedaco.items():
                        if no == "__interrupt__":
                            interrompido = True
                            yield from (_aprovacao(interrupcao) for interrupcao in atualizacao)
                            continue
                        etapa = descrever_etapa(no, atualizacao)
                        yield Evento(tipo="etapa", dados=etapa)
                        if no == "guardrail_saida":
                            if not etapa["alerta"]:
                                yield from rascunho
                            rascunho.clear()
                        if obs and (tag := _tag_do_no(no, atualizacao)):
                            tags.enter_context(obs.marcar(tags=[tag]))
        if not interrompido:
            yield self._resposta_final(config)

    def _config(self, conversa_id: str, cliente_id: str) -> dict[str, Any]:
        config: dict[str, Any] = {
            "configurable": {"thread_id": conversa_id, "cliente_id": cliente_id}
        }
        callback = self.observabilidade.callback() if self.observabilidade else None
        if callback:
            config["callbacks"] = [callback]
        return config

    def _resposta_final(self, config: dict[str, Any]) -> Evento:
        estado = self.grafo.get_state(config).values
        ultima = next(
            (m for m in reversed(estado.get("messages", [])) if isinstance(m, AIMessage)), None
        )
        return Evento(
            tipo="message_done",
            dados={
                "conteudo": str(ultima.content) if ultima else "",
                "desfecho": estado.get("desfecho"),
            },
        )


def _token(mensagem: BaseMessage, metadata: dict) -> Evento | None:
    """Só o texto que o modelo escreve para o Cliente vira token (tool calls não)."""
    if (
        metadata.get("langgraph_node") in NOS_QUE_ESCREVEM
        and isinstance(mensagem, AIMessageChunk)
        and mensagem.content
        and not mensagem.tool_call_chunks
    ):
        return Evento(tipo="token", dados={"texto": str(mensagem.content)})
    return None


def _aprovacao(interrupcao: Interrupt) -> Evento:
    valor = dict(interrupcao.value)
    return Evento(
        tipo="approval_required",
        dados={
            "pedido_id": valor["pedido_id"],
            "valor": valor["valor"],
            "probabilidade": valor["probabilidade"],
            "resumo": valor["resumo"],
            "motivo_do_gate": valor.get("motivo_do_gate"),
        },
    )


def descrever_etapa(no: str, atualizacao: Any) -> dict[str, Any]:
    """Uma linha legível sobre o que o nó decidiu, para os bastidores do chat."""
    atualizacao = atualizacao if isinstance(atualizacao, dict) else {}
    detalhe, alerta = _DESCRICOES.get(no, _sem_detalhe)(atualizacao)
    return {"no": no, "detalhe": detalhe, "alerta": alerta}


def _sem_detalhe(_: dict) -> tuple[str | None, bool]:
    return None, False


def _carregar_memoria(a: dict) -> tuple[str, bool]:
    memorias = a.get("memorias") or {}
    fatos, episodios = len(memorias.get("semantica", [])), len(memorias.get("episodica", []))
    procedural = " e instruções do Atendente" if memorias.get("procedural") else ""
    return f"{fatos} fato(s), {episodios} episódio(s){procedural}", False


def _guardrail_entrada(a: dict) -> tuple[str, bool]:
    if a.get("bloqueio"):
        return f"bloqueou: {a['bloqueio']}", True
    if a.get("mensagem_sensivel"):
        return "passou, com dado sensível protegido", True
    return "passou", False


def _recuperar_contexto(a: dict) -> tuple[str, bool]:
    documentos = dict.fromkeys(c.get("documento", "").removesuffix(".md") for c in a["contexto"])
    return f"{len(a['contexto'])} trecho(s): {', '.join(documentos) or 'nenhum'}", False


def _agente(a: dict) -> tuple[str | None, bool]:
    if decisoes := a.get("decisoes_do_gate"):
        linhas = [
            f"Gate {pedido}: {'exige Atendente' if d['exige_aprovacao'] else 'automático'} "
            f"({d['motivo']}, {d['probabilidade']:.0%})"
            for pedido, d in decisoes.items()
        ]
        return "; ".join(linhas), any(d["exige_aprovacao"] for d in decisoes.values())
    mensagens = a.get("messages") or []
    pedidas = [c["name"] for m in mensagens if isinstance(m, AIMessage) for c in m.tool_calls]
    if pedidas:
        return f"pediu: {', '.join(pedidas)}", False
    executadas = [m.name for m in mensagens if isinstance(m, ToolMessage)]
    if executadas:
        return f"executou: {', '.join(executadas)}", False
    return ("resposta candidata escrita", False) if a.get("resposta_candidata") else (None, False)


def _guardrail_saida(a: dict) -> tuple[str, bool]:
    if a.get("escalada_por"):
        return f"reprovada de novo ({a.get('motivo_da_reprovacao')}): escala", True
    if a.get("critica"):
        return f"reprovada ({a.get('motivo_da_reprovacao')}): volta para corrigir", True
    return "aprovada", False


def _salvar_memoria(a: dict) -> tuple[str, bool]:
    return (
        "memória atualizada e Conversa resumida" if a.get("resumo") else "memória atualizada"
    ), False


_DESCRICOES = {
    "carregar_memoria": _carregar_memoria,
    "guardrail_entrada": _guardrail_entrada,
    "roteador": lambda a: (a.get("intencao"), False),
    "recuperar_contexto": _recuperar_contexto,
    "gerar_resposta": lambda a: ("resposta candidata escrita", False),
    "agente": _agente,
    "guardrail_saida": _guardrail_saida,
    "escalar": lambda a: ("Ticket aberto para um Atendente", True),
    "salvar_memoria": _salvar_memoria,
}


def _tag_do_no(no: str, atualizacao: Any) -> str | None:
    """Tags do trace no Langfuse: intenção, motivo de bloqueio e escalada."""
    if not isinstance(atualizacao, dict):
        return None
    if no == "roteador" and atualizacao.get("intencao"):
        return f"intencao:{atualizacao['intencao']}"
    if no == "guardrail_entrada" and atualizacao.get("bloqueio"):
        return f"bloqueio:{atualizacao['bloqueio']}"
    if no == "escalar":
        return f"escalada:{atualizacao.get('escalada_por')}"
    return None
