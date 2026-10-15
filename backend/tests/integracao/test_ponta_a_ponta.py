"""Ponta a ponta com Postgres real: fila → worker → ExecutorDoGrafo (modelos falsos) →
checkpointer e Store do LangGraph no Postgres → mensagens, Aprovações Pendentes e Reembolsos
gravados. Só os modelos são falsos; a persistência inteira é a de produção, montada sobre o
mesmo pool que a raiz de composição usa."""

import uuid

import pytest
from langgraph.checkpoint.postgres import PostgresSaver

from ampere.acoes.aprovacoes import decidir_aprovacao, listar_pendentes
from ampere.acoes.ticket import ResumoDoTicket, StoreDeTicketsPostgres
from ampere.conversas.conversas import criar_conversa, listar_mensagens, obter_conversa
from ampere.fila.fila import enfileirar_mensagem, enfileirar_retomada
from ampere.fila.worker import processar_um_job
from ampere.grafo.construtor import Dependencias, construir_grafo
from ampere.grafo.executor import ExecutorDoGrafo
from ampere.loja.pedidos import StoreDePedidosPostgres
from ampere.memoria.salvar import MemoriasExtraidas
from ampere.memoria.store import criar_store_postgres
from ampere.nucleo.config import Config
from ampere.nucleo.falsos import JevFalso, ModeloFalso, embed_falso
from ampere.nucleo.modelos import FabricaDeModelos
from ampere.observabilidade.langfuse import Observabilidade
from ampere.rag.busca import RetrieverFalso
from tests.apoio import CHUNK_GARANTIA, tool_call

pytestmark = pytest.mark.integracao


def _semear(conn) -> None:
    conn.execute("INSERT INTO clientes (id, nome, email) VALUES ('cli_ana', 'Ana', 'ana@x.com')")
    conn.execute(
        "INSERT INTO pedidos (id, cliente_id, produto, linha, valor, status, data) VALUES "
        "('P1', 'cli_ana', 'Fone', 'acessorios', 199.90, 'entregue', '2026-08-01'), "
        "('P2', 'cli_ana', 'Notebook Vega 15', 'notebooks', 4899.90, 'entregue', '2026-08-10')"
    )


def _executor(banco: str, pool, gerador: list, jev: JevFalso) -> ExecutorDoGrafo:
    config = Config(database_url=banco, modelos_falsos=True)
    fabrica = FabricaDeModelos(
        config,
        gerador=ModeloFalso(gerador),
        trabalhador=ModeloFalso(
            [
                MemoriasExtraidas(fatos=["Tem um notebook Vega 15"], episodio="Falou de garantia"),
                ResumoDoTicket(resumo="x", categoria="outro", prioridade="baixa"),
            ]
        ),
        jev=jev,
    )
    grafo = construir_grafo(
        Dependencias(
            config=config,
            fabrica=fabrica,
            retriever=RetrieverFalso([CHUNK_GARANTIA]),
            pedidos=StoreDePedidosPostgres(pool),
            tickets=StoreDeTicketsPostgres(pool),
            observabilidade=Observabilidade(config),
        ),
        checkpointer=PostgresSaver(pool),
        store=criar_store_postgres(pool, embed_falso),
    )
    return ExecutorDoGrafo(grafo)


def test_mensagem_atravessa_fila_grafo_e_persistencia_do_langgraph(banco, pool):
    executor = _executor(
        banco, pool, ["A garantia é de 12 meses."], JevFalso(choices={"intencao": "duvida"})
    )
    with pool.connection() as conn:
        _semear(conn)
        conversa_id = criar_conversa(conn, "cli_ana")
        assert enfileirar_mensagem(conn, conversa_id, str(uuid.uuid4()), "garantia?", "cli_ana")

        assert processar_um_job(conn, executor) is True
        assert processar_um_job(conn, executor) is False

        mensagens = listar_mensagens(conn, conversa_id)
        assert [m.papel for m in mensagens] == ["cliente", "assistente"]
        assert mensagens[-1].conteudo == "A garantia é de 12 meses."
        assert obter_conversa(conn, conversa_id).status == "resolvida"

        # segundo turno: a memória do turno anterior veio do Store no Postgres (pgvector)
        assert enfileirar_mensagem(conn, conversa_id, str(uuid.uuid4()), "e o frete?", "cli_ana")
        assert processar_um_job(conn, executor) is True
        estado = executor.grafo.get_state(
            {"configurable": {"thread_id": conversa_id, "cliente_id": "cli_ana"}}
        ).values
        assert estado["memorias"]["semantica"] == ["Tem um notebook Vega 15"]
        assert len(estado["messages"]) == 4


def test_reembolso_com_aprovacao_pendente_e_retomada_pelo_atendente(banco, pool):
    executor = _executor(
        banco,
        pool,
        [tool_call("emitir_reembolso", {"pedido_id": "P2", "motivo": "defeito"}), "Aprovado!"],
        JevFalso(choices={"intencao": "transacao"}),
    )
    with pool.connection() as conn:
        _semear(conn)
        conversa_id = criar_conversa(conn, "cli_ana")
        enfileirar_mensagem(conn, conversa_id, str(uuid.uuid4()), "reembolso do P2", "cli_ana")

        processar_um_job(conn, executor)

        [pendente] = listar_pendentes(conn)
        assert pendente.pedido_id == "P2"
        assert pendente.motivo_do_gate == "valor_acima_do_limite"
        assert obter_conversa(conn, conversa_id).status == "aprovacao_pendente"
        assert conn.execute("SELECT count(*) AS n FROM reembolsos").fetchone()["n"] == 0

        decidir_aprovacao(conn, pendente.id, True)
        enfileirar_retomada(conn, conversa_id, pendente.id, True, None, "cli_ana")
        assert processar_um_job(conn, executor) is True

        assert conn.execute("SELECT count(*) AS n FROM reembolsos").fetchone()["n"] == 1
        assert listar_mensagens(conn, conversa_id)[-1].conteudo == "Aprovado!"
        assert obter_conversa(conn, conversa_id).status == "resolvida"
