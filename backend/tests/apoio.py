"""Apoio compartilhado pelos testes do grafo, do executor e de ponta a ponta: um cenário
com modelos falsos, Jev falso, checkpointer e Store em memória."""

from datetime import date
from decimal import Decimal

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from ampere.acoes.ticket import ResumoDoTicket, StoreDeTicketsEmMemoria
from ampere.grafo.construtor import Dependencias, construir_grafo
from ampere.loja.pedidos import Pedido, Reembolso, StoreDePedidosEmMemoria
from ampere.memoria.salvar import MemoriasExtraidas
from ampere.memoria.store import criar_store_em_memoria
from ampere.nucleo.config import Config
from ampere.nucleo.falsos import JevFalso, ModeloFalso, embed_falso
from ampere.nucleo.modelos import FabricaDeModelos
from ampere.observabilidade.langfuse import Observabilidade
from ampere.rag.busca import RetrieverFalso
from ampere.rag.chunkers import Chunk

CHUNK_GARANTIA = Chunk(
    texto="A garantia de notebooks é de 12 meses.",
    documento="garantia_notebooks.md",
    categoria="garantia",
    produto="notebooks",
    vigencia="2026-01-01",
    tipo="politica",
    indice=0,
)
PEDIDOS = [
    Pedido(
        id="P1",
        cliente_id="cli_ana",
        produto="Fone Ampère Beat",
        linha="acessorios",
        valor=Decimal("199.90"),
        status="entregue",
        data=date(2026, 8, 1),
    ),
    Pedido(
        id="P2",
        cliente_id="cli_ana",
        produto="Notebook Ampère Vega 15",
        linha="notebooks",
        valor=Decimal("4899.90"),
        status="entregue",
        data=date(2026, 8, 10),
    ),
]
MEMORIAS = MemoriasExtraidas(fatos=["Tem um notebook Vega 15"], episodio="Perguntou sobre garantia")
TICKET = ResumoDoTicket(resumo="Cliente quer humano", categoria="outro", prioridade="media")


def tool_call(nome: str, args: dict, id: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": nome, "args": args, "id": id}])


class Cenario:
    """Monta o grafo com falsos e expõe o que os testes precisam inspecionar."""

    def __init__(
        self,
        *,
        gerador: list | None = None,
        trabalhador: list | None = None,
        jev: JevFalso | None = None,
        config: Config | None = None,
        reembolsos: list[Reembolso] | None = None,
    ) -> None:
        self.config = config or Config(modelos_falsos=True)
        self.gerador = ModeloFalso(gerador or ["Resposta padrão."])
        self.trabalhador = ModeloFalso(trabalhador or [MEMORIAS, TICKET])
        self.jev = jev or JevFalso(choices={"intencao": "duvida"})
        self.fabrica = FabricaDeModelos(
            self.config, gerador=self.gerador, trabalhador=self.trabalhador, jev=self.jev
        )
        self.retriever = RetrieverFalso([CHUNK_GARANTIA])
        self.pedidos = StoreDePedidosEmMemoria(PEDIDOS, reembolsos)
        self.tickets = StoreDeTicketsEmMemoria()
        self.store = criar_store_em_memoria(embed_falso)
        self.checkpointer = InMemorySaver()
        self.grafo = construir_grafo(
            Dependencias(
                config=self.config,
                fabrica=self.fabrica,
                retriever=self.retriever,
                pedidos=self.pedidos,
                tickets=self.tickets,
                observabilidade=Observabilidade(self.config),
            ),
            checkpointer=self.checkpointer,
            store=self.store,
        )

    def invocar_config(self, conversa_id="conversa-1", cliente_id="cli_ana"):
        return {"configurable": {"thread_id": conversa_id, "cliente_id": cliente_id}}

    def turno(self, mensagem: str, *, conversa_id="conversa-1", cliente_id="cli_ana") -> dict:
        return self.grafo.invoke(
            {
                "messages": [HumanMessage(mensagem)],
                "cliente_id": cliente_id,
                "conversa_id": conversa_id,
            },
            self.invocar_config(conversa_id, cliente_id),
        )


def ultima_resposta(estado: dict) -> str:
    return estado["messages"][-1].content
