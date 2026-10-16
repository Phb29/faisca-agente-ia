"""Ações: Pedidos, Gate de Aprovação do Reembolso e Ticket (sem grafo, sem banco)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from langchain_core.messages import AIMessage, HumanMessage

from ampere.acoes.reembolso import avaliar_gate, motivo_para_recusar
from ampere.acoes.ticket import ResumoDoTicket, StoreDeTicketsEmMemoria, abrir_ticket
from ampere.loja.pedidos import Pedido, Reembolso, StoreDePedidosEmMemoria
from ampere.nucleo.falsos import JevFalso, ModeloFalso

JANELA = {"janela_dias": 30, "limiar": 0.5}
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
        pedido_id="P0",
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


def test_gate_valor_acima_do_limite_exige_aprovacao_mas_ainda_consulta_o_jev():
    jev = JevFalso(nouls={"exige_aprovacao": 0.3})

    decisao = avaliar_gate(
        jev, valor=Decimal("500"), valor_limite=300.0, reembolsos_recentes=0, **JANELA
    )

    assert (decisao.exige_aprovacao, decisao.probabilidade, decisao.motivo) == (
        True,
        0.3,
        "valor_acima_do_limite",
    )
    estado, _ = jev.chamadas[0]
    assert estado["valor_acima_do_limite"] is True
    assert estado["reembolsos_nos_ultimos_30_dias"] == 0


def test_gate_reembolso_recente_exige_aprovacao():
    decisao = avaliar_gate(
        JevFalso(), valor=Decimal("50"), valor_limite=300.0, reembolsos_recentes=1, **JANELA
    )

    assert decisao.exige_aprovacao is True
    assert decisao.motivo == "reembolso_recente"


def test_gate_abaixo_do_limite_pergunta_ao_jev_e_respeita_limiar():
    jev = JevFalso(nouls={"exige_aprovacao": 0.5})

    decisao = avaliar_gate(
        jev, valor=Decimal("120"), valor_limite=300.0, reembolsos_recentes=0, **JANELA
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
        **JANELA,
    )

    assert decisao.exige_aprovacao is False
    assert decisao.probabilidade == 0.2
    assert decisao.motivo == "automatico"


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


def test_pedido_aguardando_pagamento_ou_ja_reembolsado_nao_pode_ser_reembolsado():
    aguardando = Pedido(
        id="P3",
        cliente_id="cli_ana",
        produto="Capa",
        linha="acessorios",
        valor=Decimal("89.90"),
        status="aguardando_pagamento",
        data=date(2026, 9, 1),
    )
    store = StoreDePedidosEmMemoria([*PEDIDOS, aguardando])

    assert motivo_para_recusar(PEDIDOS[0], store) is None
    assert "pagamento" in motivo_para_recusar(aguardando, store)

    store.registrar_reembolso(Reembolso(pedido_id="P1", cliente_id="cli_ana", valor=Decimal("1")))

    assert "já foi reembolsado" in motivo_para_recusar(PEDIDOS[0], store)
    assert store.reembolso_do_pedido("cli_bruno", "P1") is None


def test_resumo_do_pedido_usa_o_formato_que_o_cliente_le():
    notebook = PEDIDOS[1]

    assert notebook.resumo() == (
        "Pedido P2: Notebook (notebooks), R$ 4.899,90, status em transporte, feito em 01/09/2026"
    )


def test_store_de_pedidos_recusa_o_segundo_reembolso_do_mesmo_pedido():
    store = StoreDePedidosEmMemoria(PEDIDOS)
    reembolso = Reembolso(pedido_id="P1", cliente_id="cli_ana", valor=Decimal("199.90"))

    assert store.registrar_reembolso(reembolso) is True
    assert store.registrar_reembolso(reembolso) is False
    assert len(store.reembolsos_recentes("cli_ana")) == 1
