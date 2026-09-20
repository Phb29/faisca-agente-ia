"""Ações: Pedidos, Gate de Aprovação do Reembolso e Ticket (sem grafo, sem banco)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from langchain_core.messages import AIMessage, HumanMessage

from ampere.acoes.pedidos import Pedido, Reembolso, StoreDePedidosEmMemoria
from ampere.acoes.reembolso import DecisaoDoGate, avaliar_gate
from ampere.acoes.ticket import ResumoDoTicket, StoreDeTicketsEmMemoria, abrir_ticket
from ampere.nucleo.falsos import JevFalso, ModeloFalso

PEDIDOS = [
    Pedido(
        id="P1",
        cliente_id="cli_ana",
        produto="Fone",
        linha="acessorios",
        valor=Decimal("199.90"),
        status="entregue",
        data=date(2026, 8, 1),
    ),
    Pedido(
        id="P2",
        cliente_id="cli_bruno",
        produto="Notebook",
        linha="notebooks",
        valor=Decimal("4899.90"),
        status="em_transporte",
        data=date(2026, 9, 1),
    ),
]


def test_store_de_pedidos_so_enxerga_pedidos_do_cliente_atual():
    store = StoreDePedidosEmMemoria(PEDIDOS)

    assert [p.id for p in store.listar("cli_ana")] == ["P1"]
    assert store.obter("cli_ana", "P2") is None
    assert store.obter("cli_bruno", "P2").produto == "Notebook"


def test_store_de_pedidos_registra_reembolso_e_lista_os_recentes():
    store = StoreDePedidosEmMemoria(PEDIDOS)
    antigo = Reembolso(
        pedido_id="P1",
        cliente_id="cli_ana",
        valor=Decimal("10"),
        criado_em=datetime.now(UTC) - timedelta(days=90),
    )
    store.registrar_reembolso(antigo)

    store.registrar_reembolso(
        Reembolso(pedido_id="P1", cliente_id="cli_ana", valor=Decimal("199.90"))
    )

    recentes = store.reembolsos_recentes("cli_ana", dias=30)
    assert len(recentes) == 1
    assert recentes[0].valor == Decimal("199.90")


def test_gate_valor_acima_do_limite_exige_aprovacao_sem_consultar_jev():
    jev = JevFalso(nouls={"exige_aprovacao": 0.0})

    decisao = avaliar_gate(
        jev, valor=Decimal("500"), valor_limite=300.0, reembolsos_recentes=0, limiar=0.5
    )

    assert decisao == DecisaoDoGate(
        exige_aprovacao=True, probabilidade=1.0, motivo="valor_acima_do_limite"
    )
    assert jev.chamadas == []


def test_gate_reembolso_recente_exige_aprovacao():
    decisao = avaliar_gate(
        JevFalso(), valor=Decimal("50"), valor_limite=300.0, reembolsos_recentes=1, limiar=0.5
    )

    assert decisao.exige_aprovacao is True
    assert decisao.motivo == "reembolso_recente"


def test_gate_abaixo_do_limite_pergunta_ao_jev_e_respeita_limiar():
    jev = JevFalso(nouls={"exige_aprovacao": 0.5})

    decisao = avaliar_gate(
        jev, valor=Decimal("120"), valor_limite=300.0, reembolsos_recentes=0, limiar=0.5
    )

    assert decisao.exige_aprovacao is True
    assert decisao.probabilidade == 0.5
    assert decisao.motivo == "gate"
    estado, perguntas = jev.chamadas[0]
    assert estado["valor"] == 120.0
    assert set(perguntas) == {"exige_aprovacao"}


def test_gate_abaixo_do_limiar_libera_automaticamente():
    decisao = avaliar_gate(
        JevFalso(nouls={"exige_aprovacao": 0.2}),
        valor=Decimal("120"),
        valor_limite=300.0,
        reembolsos_recentes=0,
        limiar=0.5,
    )

    assert decisao.exige_aprovacao is False
    assert decisao.probabilidade == 0.2


def test_abrir_ticket_usa_trabalhador_e_grava_no_store():
    trabalhador = ModeloFalso(
        [ResumoDoTicket(resumo="Frete atrasado", categoria="frete", prioridade="alta")]
    )
    tickets = StoreDeTicketsEmMemoria()
    mensagens = [HumanMessage("meu frete atrasou"), AIMessage("vou verificar")]

    ticket = abrir_ticket(
        trabalhador, tickets, conversa_id="c1", cliente_id="cli_ana", messages=mensagens
    )

    assert ticket.categoria == "frete"
    assert ticket.prioridade == "alta"
    assert tickets.listar()[0].resumo == "Frete atrasado"
    prompt = trabalhador.chamadas[0][0].content
    assert "meu frete atrasou" in prompt
