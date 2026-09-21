"""Eval do agente: um turno do grafo real por cenário, comparado por código e pelo juiz.

Intenção, Ação e desfecho são comparados por código com o estado final do grafo; a resposta
final passa pelo juiz (`julgar_resolucao`). O grafo roda com modelos e Jev reais, retriever
do Qdrant, e checkpointer, Store, Pedidos e Tickets em memória (um conjunto novo por
cenário, para um cenário não contaminar o outro).
"""

import csv
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from langchain_core.messages import AIMessage
from pydantic import BaseModel, field_validator

from ampere.evals.juiz import Veredito, julgar_resolucao
from ampere.nucleo.config import Config

PASTA_DADOS = Path(__file__).parent / "dados"
NOME_DATASET = "golden_agente"
SEM_ACAO = "nenhuma"
APROVACAO_PENDENTE = "Aprovação Pendente"
VERDADEIROS = {"sim", "s", "true", "1", "verdadeiro", "yes"}


class Cenario(BaseModel):
    id: str
    mensagem: str
    cliente_id: str
    pedido_id: str | None = None
    memorias: str = ""
    intencao_esperada: str | None = None
    acao_esperada: str = SEM_ACAO
    desfecho_esperado: str
    guardrail_bloqueia: bool = False

    @field_validator("pedido_id", "intencao_esperada", mode="before")
    @classmethod
    def _vazio_vira_none(cls, valor: Any) -> Any:
        return None if isinstance(valor, str) and not valor.strip() else valor

    @field_validator("acao_esperada", mode="before")
    @classmethod
    def _vazio_vira_nenhuma(cls, valor: Any) -> Any:
        return SEM_ACAO if isinstance(valor, str) and not valor.strip() else valor

    @field_validator("guardrail_bloqueia", mode="before")
    @classmethod
    def _sim_nao(cls, valor: Any) -> Any:
        return valor.strip().lower() in VERDADEIROS if isinstance(valor, str) else valor


def carregar_golden_agente(caminho: Path = PASTA_DADOS / "golden_agente.csv") -> list[Cenario]:
    with Path(caminho).open(encoding="utf-8", newline="") as arquivo:
        return [Cenario.model_validate(linha) for linha in csv.DictReader(arquivo)]


# --- comparação por código -------------------------------------------------------------------


@dataclass(frozen=True)
class Comparacao:
    intencao_ok: bool
    acao_ok: bool
    desfecho_ok: bool
    intencao: str
    acao: str
    desfecho: str
    bloqueado: bool

    @property
    def tudo_ok(self) -> bool:
        return self.intencao_ok and self.acao_ok and self.desfecho_ok


def comparar(cenario: Cenario, estado_final: dict) -> Comparacao:
    """Puro. A Ação observada é a primeira tomada; a interrupção vale como Aprovação Pendente."""
    bloqueado = bool(estado_final.get("bloqueio"))
    intencao = estado_final.get("intencao") or SEM_ACAO
    acoes = list(estado_final.get("acoes_tomadas") or [])
    acao = acoes[0] if acoes else SEM_ACAO
    if estado_final.get("__interrupt__"):
        desfecho = APROVACAO_PENDENTE
    else:
        desfecho = estado_final.get("desfecho") or "nenhum"

    if cenario.guardrail_bloqueia and cenario.intencao_esperada is None:
        intencao_ok = bloqueado
    else:
        intencao_ok = intencao == (cenario.intencao_esperada or SEM_ACAO)
    return Comparacao(
        intencao_ok=intencao_ok,
        acao_ok=acao == cenario.acao_esperada,
        desfecho_ok=desfecho == cenario.desfecho_esperado,
        intencao=intencao,
        acao=acao,
        desfecho=desfecho,
        bloqueado=bloqueado,
    )


def resposta_final(estado_final: dict) -> str:
    """Última mensagem do assistente com texto; vazia quando o turno parou numa interrupção."""
    for mensagem in reversed(estado_final.get("messages") or []):
        if isinstance(mensagem, AIMessage):
            return str(mensagem.content)
    return ""


@dataclass(frozen=True)
class MemoriasIniciais:
    semantica: list[str]
    procedural: str


def interpretar_memorias(texto: str) -> MemoriasIniciais:
    """Texto livre do CSV: 'Memória Procedural: ...' vira procedural; o resto, fato semântico."""
    procedural = ""
    restante = texto.strip()
    encontrado = re.search(r"Memória Procedural:\s*(.*?)(?=Memória Semântica:|$)", restante, re.S)
    if encontrado:
        procedural = encontrado.group(1).strip()
        restante = re.sub(
            r"Memória Procedural:.*?(?=Memória Semântica:|$)", "", restante, flags=re.S
        )
    restante = re.sub(r"Memória Semântica:\s*", "", restante).strip()
    return MemoriasIniciais(semantica=[restante] if restante else [], procedural=procedural)


# --- execução -----------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoDoCenario:
    cenario: Cenario
    comparacao: Comparacao
    resposta: str
    veredito: Veredito | None

    def linha(self) -> dict:
        return {
            "id": self.cenario.id,
            "intencao_esperada": self.cenario.intencao_esperada,
            "intencao": self.comparacao.intencao,
            "intencao_ok": self.comparacao.intencao_ok,
            "acao_esperada": self.cenario.acao_esperada,
            "acao": self.comparacao.acao,
            "acao_ok": self.comparacao.acao_ok,
            "desfecho_esperado": self.cenario.desfecho_esperado,
            "desfecho": self.comparacao.desfecho,
            "desfecho_ok": self.comparacao.desfecho_ok,
            "bloqueado": self.comparacao.bloqueado,
            "resposta": self.resposta,
            "aprovada": self.veredito.aprovada if self.veredito else None,
            "critica": self.veredito.critica if self.veredito else None,
        }


class ExecutorDeCenarios:
    """Monta as dependências reais uma vez e um grafo novo (memória limpa) por cenário."""

    def __init__(self, config: Config, composicao: "Composicao") -> None:
        from ampere.rag.embedders import criar_embedder

        self.config = config
        self.composicao = composicao
        self.observabilidade = composicao.observabilidade
        self.embed = criar_embedder("minilm", config).embed

    def executar(self, cenario: Cenario) -> ResultadoDoCenario:
        from langchain_core.messages import HumanMessage
        from langgraph.checkpoint.memory import InMemorySaver

        from ampere.acoes.pedidos import Pedido, Reembolso, StoreDePedidosEmMemoria
        from ampere.acoes.ticket import StoreDeTicketsEmMemoria
        from ampere.fila.seed import PEDIDOS, REEMBOLSOS
        from ampere.memoria.salvar import escrever_procedural
        from ampere.memoria.store import criar_store_em_memoria, namespace_semantica

        store = criar_store_em_memoria(self.embed)
        iniciais = interpretar_memorias(cenario.memorias)
        for fato in iniciais.semantica:
            store.put(namespace_semantica(cenario.cliente_id), str(uuid4()), {"texto": fato})
        if iniciais.procedural:
            escrever_procedural(store, cenario.cliente_id, iniciais.procedural)

        grafo = self.composicao.construir_grafo(
            pedidos=StoreDePedidosEmMemoria(
                [Pedido(**p) for p in PEDIDOS], [Reembolso(**r) for r in REEMBOLSOS]
            ),
            tickets=StoreDeTicketsEmMemoria(),
            checkpointer=InMemorySaver(),
            store=store,
        )
        conversa_id = f"eval-{cenario.id}-{uuid4().hex[:8]}"
        invocacao: dict[str, Any] = {
            "configurable": {"thread_id": conversa_id, "cliente_id": cenario.cliente_id}
        }
        callback = self.observabilidade.callback()
        if callback is not None:
            invocacao["callbacks"] = [callback]
        with self.observabilidade.contexto_da_conversa(
            conversa_id, cenario.cliente_id, tags=["eval", "golden_agente"]
        ):
            estado = grafo.invoke(
                {
                    "messages": [HumanMessage(cenario.mensagem)],
                    "cliente_id": cenario.cliente_id,
                    "conversa_id": conversa_id,
                },
                invocacao,
            )
        comparacao = comparar(cenario, estado)
        resposta = resposta_final(estado)
        veredito = None
        if resposta:
            veredito = julgar_resolucao(
                self.fabrica.juiz(), mensagem=cenario.mensagem, resposta=resposta
            )
        return ResultadoDoCenario(cenario, comparacao, resposta, veredito)


class Composicao(Protocol):
    """O que a raiz de composição (`ampere.cli`) entrega ao eval: o grafo real montado com
    os modelos e o retriever de produção, sem este módulo importar de `ampere.grafo`."""

    observabilidade: Any

    def construir_grafo(
        self, *, pedidos: Any, tickets: Any, checkpointer: Any, store: Any
    ) -> Any: ...


def rodar(config: Config, composicao: Composicao, *, amostra: int | None = None) -> list[dict]:
    from rich.console import Console
    from rich.table import Table

    from ampere.evals.datasets import cliente_langfuse

    console = Console()
    cenarios = carregar_golden_agente()[:amostra]
    executor = ExecutorDeCenarios(config, composicao)
    resultados: list[ResultadoDoCenario] = []
    for cenario in cenarios:
        console.print(f"[dim]{cenario.id}: {cenario.mensagem[:70]}")
        resultados.append(executor.executar(cenario))

    tabela = Table(title=f"Eval do agente ({len(resultados)} cenários)")
    for coluna in ("Id", "Intenção", "Ação", "Desfecho", "Juiz", "Crítica"):
        tabela.add_column(coluna, overflow="fold")
    for r in resultados:
        c = r.comparacao
        tabela.add_row(
            r.cenario.id,
            _par(r.cenario.intencao_esperada or "bloqueio", c.intencao, c.intencao_ok),
            _par(r.cenario.acao_esperada, c.acao, c.acao_ok),
            _par(r.cenario.desfecho_esperado, c.desfecho, c.desfecho_ok),
            "—" if r.veredito is None else _marca(r.veredito.aprovada),
            r.veredito.critica if r.veredito else "(sem resposta final)",
        )
    console.print(tabela)
    console.print(_resumo(resultados))

    cliente = cliente_langfuse(config)
    if cliente is not None:
        _publicar(cliente, resultados)
        console.print("[dim]Langfuse: dataset e run publicados.")
    executor.observabilidade.encerrar()
    return [r.linha() for r in resultados]


def _resumo(resultados: Sequence[ResultadoDoCenario]) -> str:
    n = len(resultados) or 1
    julgados = [r for r in resultados if r.veredito is not None]
    aprovadas = sum(r.veredito.aprovada for r in julgados if r.veredito)
    return (
        "Acerto por dimensão: "
        f"intenção {sum(r.comparacao.intencao_ok for r in resultados) / n:.0%}, "
        f"Ação {sum(r.comparacao.acao_ok for r in resultados) / n:.0%}, "
        f"desfecho {sum(r.comparacao.desfecho_ok for r in resultados) / n:.0%}, "
        f"tudo {sum(r.comparacao.tudo_ok for r in resultados) / n:.0%}. "
        f"Juiz aprovou {aprovadas}/{len(julgados)} respostas."
    )


def _publicar(cliente: Any, resultados: Sequence[ResultadoDoCenario]) -> None:
    from ampere.evals.datasets import publicar_dataset, publicar_run

    publicar_dataset(
        cliente,
        NOME_DATASET,
        [
            {
                "id": r.cenario.id,
                "input": {
                    "id": r.cenario.id,
                    "mensagem": r.cenario.mensagem,
                    "cliente_id": r.cenario.cliente_id,
                    "pedido_id": r.cenario.pedido_id,
                    "memorias": r.cenario.memorias,
                },
                "expected_output": {
                    "intencao": r.cenario.intencao_esperada,
                    "acao": r.cenario.acao_esperada,
                    "desfecho": r.cenario.desfecho_esperado,
                    "guardrail_bloqueia": r.cenario.guardrail_bloqueia,
                },
            }
            for r in resultados
        ],
    )
    run: dict[str, tuple[Any, dict]] = {}
    for r in resultados:
        c = r.comparacao
        scores: dict[str, tuple[Any, str | None]] = {
            "intencao_ok": (
                c.intencao_ok,
                f"esperada {r.cenario.intencao_esperada}, obtida {c.intencao}",
            ),
            "acao_ok": (c.acao_ok, f"esperada {r.cenario.acao_esperada}, obtida {c.acao}"),
            "desfecho_ok": (
                c.desfecho_ok,
                f"esperado {r.cenario.desfecho_esperado}, obtido {c.desfecho}",
            ),
        }
        if r.veredito is not None:
            scores["resolucao"] = (r.veredito.aprovada, r.veredito.critica)
        run[r.cenario.id] = ({"resposta": r.resposta, **c.__dict__}, scores)
    publicar_run(cliente, NOME_DATASET, f"agente-{uuid4().hex[:8]}", run)


def _par(esperado: str, obtido: str, ok: bool) -> str:
    return f"{esperado} → {obtido} {_marca(ok)}"


def _marca(ok: bool) -> str:
    return "[green]✓[/green]" if ok else "[red]✗[/red]"
