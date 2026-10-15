"""Eval do agente: um turno do grafo real por cenário, comparado por código e pelo juiz.

Intenção, Ação e desfecho são comparados por código com o estado final do grafo; a resposta
final passa pelo juiz (`julgar_resolucao`). O grafo roda com modelos e Jev reais, retriever
do Qdrant, e checkpointer, Store, Pedidos e Tickets em memória (um conjunto novo por
cenário, para um cenário não contaminar o outro).

Os passos de cada cenário soltam o nome de cada nó quando ele começa, para a amostra ao
vivo mostrar o grafo andando (ver `ampere.evals.ao_vivo`), e `rodar` devolve o relatório
que o CLI grava.
"""

import csv
import random
import re
import time
from collections.abc import Generator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from pydantic import BaseModel, field_validator

from ampere.acoes.ticket import StoreDeTickets, StoreDeTicketsEmMemoria
from ampere.evals.juiz import Veredito, julgar_resolucao
from ampere.evals.relatorio import PassosDoCaso, Relatorio, Sorteado, consumir, contexto_base
from ampere.loja.pedidos import Pedido, Reembolso, StoreDePedidos, StoreDePedidosEmMemoria
from ampere.loja.seed import PEDIDOS, REEMBOLSOS
from ampere.memoria.procedural import escrever_procedural
from ampere.memoria.store import criar_store_em_memoria, namespace_semantica
from ampere.nucleo.config import Config
from ampere.observabilidade.langfuse import Observabilidade
from ampere.rag.embedders import criar_embedder

PASTA_DADOS = Path(__file__).parent / "dados"
NOME_DATASET = "golden_agente"
SEM_ACAO = "nenhuma"
APROVACAO_PENDENTE = "Aprovação Pendente"
VERDADEIROS = {"sim", "s", "true", "1", "verdadeiro", "yes"}
PROMPTS_DO_AGENTE = (
    "agente",
    "gerar_resposta",
    "self_querying",
    "extrair_memorias",
    "resumir_conversa",
    "resumir_ticket",
    "juiz_resolucao",
)
GRUPOS_DA_AMOSTRA = (("duvida",), ("transacao",), ("bloqueio", "quer_humano"))


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


def _acoes_presas_no_gate(estado_final: dict) -> list[str]:
    """Nomes dos tool_calls da última AIMessage: pedidos que pararam no Gate sem atualizar
    `acoes_tomadas` (a interrupção acontece no meio de `_executar_acoes`, antes do `Command`)."""
    for mensagem in reversed(estado_final.get("messages") or []):
        if isinstance(mensagem, AIMessage):
            return [chamada["name"] for chamada in mensagem.tool_calls]
    return []


def comparar(cenario: Cenario, estado_final: dict) -> Comparacao:
    """Puro. A Ação observada é a primeira tomada; a interrupção vale como Aprovação Pendente,
    e a Ação parada no Gate conta como tomada."""
    bloqueado = bool(estado_final.get("bloqueio"))
    intencao = estado_final.get("intencao") or SEM_ACAO
    interrompido = bool(estado_final.get("__interrupt__"))
    acoes = list(estado_final.get("acoes_tomadas") or [])
    if interrompido:
        acoes += _acoes_presas_no_gate(estado_final)
    acao = acoes[0] if acoes else SEM_ACAO
    desfecho = APROVACAO_PENDENTE if interrompido else (estado_final.get("desfecho") or "nenhum")

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
    caminho: list[str] = field(default_factory=list)
    duracao_s: float = 0.0


class ExecutorDeCenarios:
    """Monta as dependências reais uma vez e um grafo novo (memória limpa) por cenário."""

    def __init__(self, config: Config, composicao: "Composicao") -> None:
        self.config = config
        self.composicao = composicao
        self.observabilidade = composicao.observabilidade
        self.embed = criar_embedder("minilm", config).embed

    def executar(self, cenario: Cenario) -> ResultadoDoCenario:
        return consumir(self.passos(cenario))

    def passos(self, cenario: Cenario) -> Generator[str, None, ResultadoDoCenario]:
        """Roda o cenário soltando o nome de cada nó do grafo quando ele começa e, no fim,
        "juiz" antes do veredito. O estado final é o mesmo que o `invoke` devolveria: o
        snapshot do checkpointer mais a interrupção do Gate, que só chega pelo stream."""
        inicio = time.perf_counter()
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
        caminho: list[str] = []
        interrupcao: Any = None
        with self.observabilidade.contexto_da_conversa(
            conversa_id, cenario.cliente_id, tags=["eval", "golden_agente"]
        ):
            fluxo = grafo.stream(
                {
                    "messages": [HumanMessage(cenario.mensagem)],
                    "cliente_id": cenario.cliente_id,
                    "conversa_id": conversa_id,
                },
                invocacao,
                stream_mode=["tasks", "updates"],
            )
            for modo, pedaco in fluxo:
                if modo == "tasks":
                    # O evento de início traz `input`; o de fim traz `result` ou `error`.
                    if "input" in pedaco and not pedaco["name"].startswith("__"):
                        yield pedaco["name"]
                    continue
                for no, valor in pedaco.items():
                    if no == "__interrupt__":
                        interrupcao = valor
                    else:
                        caminho.append(no)
        estado = dict(grafo.get_state(invocacao).values)
        if interrupcao:
            estado["__interrupt__"] = interrupcao
        comparacao = comparar(cenario, estado)
        resposta = resposta_final(estado)
        veredito = None
        if resposta:
            yield "juiz"
            veredito = julgar_resolucao(
                self.composicao.juiz(), mensagem=cenario.mensagem, resposta=resposta
            )
        return ResultadoDoCenario(
            cenario,
            comparacao,
            resposta,
            veredito,
            caminho=caminho,
            duracao_s=time.perf_counter() - inicio,
        )


class Composicao(Protocol):
    """O que a raiz de composição (`ampere.cli`) entrega ao eval: o grafo real montado com
    os modelos e o retriever de produção, e o juiz, sem este módulo importar de
    `ampere.grafo`."""

    observabilidade: Observabilidade

    def juiz(self) -> BaseChatModel: ...

    def construir_grafo(
        self,
        *,
        pedidos: StoreDePedidos,
        tickets: StoreDeTickets,
        checkpointer: BaseCheckpointSaver,
        store: BaseStore,
    ) -> CompiledStateGraph: ...


# --- relatório e amostra ao vivo ------------------------------------------------------------


def grupo_do_cenario(cenario: Cenario) -> str:
    if cenario.guardrail_bloqueia:
        return "bloqueio"
    return cenario.intencao_esperada or "bloqueio"


def caso_agente(resultado: ResultadoDoCenario) -> dict:
    cenario, c = resultado.cenario, resultado.comparacao
    return {
        "id": cenario.id,
        "texto": cenario.mensagem,
        "grupo": grupo_do_cenario(cenario),
        "mensagem": cenario.mensagem,
        "esperado": {
            "intencao": cenario.intencao_esperada,
            "acao": cenario.acao_esperada,
            "desfecho": cenario.desfecho_esperado,
        },
        "obtido": {"intencao": c.intencao, "acao": c.acao, "desfecho": c.desfecho},
        "ok": {"intencao": c.intencao_ok, "acao": c.acao_ok, "desfecho": c.desfecho_ok},
        "bloqueado": c.bloqueado,
        "caminho": list(resultado.caminho),
        "resposta": resultado.resposta,
        "juiz": resultado.veredito.model_dump() if resultado.veredito else None,
        "duracao_s": round(resultado.duracao_s, 2),
        "erro": None,
    }


def resumo_agente(casos: Sequence[dict]) -> dict:
    """Taxas de acerto sobre os casos sem erro; `erros` conta os que falharam."""
    validos = [c for c in casos if not c.get("erro")]
    n = len(validos)

    def taxa(chave: str) -> float:
        return sum(c["ok"][chave] for c in validos) / n if n else 0.0

    julgados = [c for c in validos if c["juiz"] is not None]
    return {
        "n": n,
        "erros": len(casos) - n,
        "intencao": taxa("intencao"),
        "acao": taxa("acao"),
        "desfecho": taxa("desfecho"),
        "tudo": sum(all(c["ok"].values()) for c in validos) / n if n else 0.0,
        "juiz_aprovadas": sum(c["juiz"]["aprovada"] for c in julgados),
        "julgados": len(julgados),
    }


def sortear_amostra(
    rng: random.Random, cenarios: Sequence[Cenario] | None = None
) -> list[Sorteado]:
    """Um cenário de dúvida, um de transação e um de bloqueio ou de pedido de humano."""
    cenarios = list(cenarios) if cenarios is not None else carregar_golden_agente()
    escolhidos = [
        rng.choice([c for c in cenarios if grupo_do_cenario(c) in grupos])
        for grupos in GRUPOS_DA_AMOSTRA
    ]
    return [
        Sorteado(id=c.id, texto=c.mensagem, grupo=grupo_do_cenario(c), item=c) for c in escolhidos
    ]


def caso_ao_vivo(sorteado: Sorteado, executor: ExecutorDeCenarios) -> PassosDoCaso:
    resultado = yield from executor.passos(sorteado.item)
    return caso_agente(resultado)


def rodar(config: Config, composicao: Composicao, *, amostra: int | None = None) -> Relatorio:
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
    casos = [caso_agente(r) for r in resultados]
    contexto = contexto_base(config, prompts=PROMPTS_DO_AGENTE, n=len(resultados))
    return Relatorio(contexto, resumo_agente(casos), casos)


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
