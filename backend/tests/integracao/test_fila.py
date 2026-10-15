"""Fila no Postgres: idempotência, SKIP LOCKED com dois workers, e o worker gravando
mensagens e Aprovações Pendentes antes de publicar os eventos."""

import asyncio
import threading

import pytest

from ampere.acoes.aprovacoes import listar_pendentes
from ampere.conversas.conversas import criar_conversa, listar_mensagens, obter_conversa
from ampere.fila.eventos import Evento, canal, escutar, publicar
from ampere.fila.executor import ExecutorFalso
from ampere.fila.fila import CANAL_DA_FILA, enfileirar_mensagem
from ampere.fila.worker import processar_um_job, rodar_worker
from ampere.nucleo.banco import conectar

pytestmark = pytest.mark.integracao


def _contar(conn, tabela: str, **filtros) -> int:
    where = " AND ".join(f"{k} = %({k})s" for k in filtros) or "TRUE"
    row = conn.execute(f"SELECT count(*) AS n FROM {tabela} WHERE {where}", filtros).fetchone()
    return row["n"]


def test_enfileirar_mesmo_message_id_duas_vezes_grava_uma_vez(banco):
    with conectar(banco) as conn:
        conversa_id = criar_conversa(conn, "c1")
        conn.commit()

        primeira = enfileirar_mensagem(conn, conversa_id, "msg-1", "oi", "c1")
        segunda = enfileirar_mensagem(conn, conversa_id, "msg-1", "oi de novo", "c1")

        assert primeira is True
        assert segunda is False
        assert _contar(conn, "fila_de_jobs") == 1
        assert _contar(conn, "mensagens") == 1
        assert listar_mensagens(conn, conversa_id)[0].conteudo == "oi"


def test_dois_workers_concorrentes_processam_cada_job_exatamente_uma_vez(banco):
    with conectar(banco) as conn:
        conversa_id = criar_conversa(conn, "c1")
        for i in range(10):
            enfileirar_mensagem(conn, conversa_id, f"msg-{i}", f"mensagem {i}", "c1")
        conn.commit()

    vistos: list[int] = []
    tranca = threading.Lock()

    def eventos_do_job(job):
        with tranca:
            vistos.append(job.id)
        return [Evento(tipo="message_done", dados={"conteudo": f"resposta ao job {job.id}"})]

    executor = ExecutorFalso(eventos_do_job)
    parar = threading.Event()
    threads = [
        threading.Thread(
            target=rodar_worker,
            args=(banco, executor),
            kwargs={"intervalo": 0.05, "parar": parar},
        )
        for _ in range(2)
    ]
    for t in threads:
        t.start()

    with conectar(banco, autocommit=True) as conn:
        for _ in range(200):
            if _contar(conn, "fila_de_jobs", status="concluido") == 10:
                break
            threading.Event().wait(0.05)
        parar.set()
        for t in threads:
            t.join(timeout=5)

        assert sorted(vistos) == sorted(set(vistos))
        assert len(vistos) == 10
        assert _contar(conn, "fila_de_jobs", status="concluido") == 10
        assert _contar(conn, "fila_de_jobs", status="erro") == 0
        assert _contar(conn, "mensagens", papel="assistente") == 10


def test_message_done_grava_mensagem_do_assistente_antes_de_publicar(banco):
    with conectar(banco) as conn:
        conversa_id = criar_conversa(conn, "c1")
        enfileirar_mensagem(conn, conversa_id, "msg-1", "oi", "c1")
        conn.commit()

    def eventos_do_job(job):
        return [
            Evento(tipo="token", dados={"texto": "olá"}),
            Evento(tipo="message_done", dados={"conteudo": "olá, tudo bem?"}),
        ]

    recebidos = _capturar_eventos(banco, conversa_id)
    assert _processar(banco, ExecutorFalso(eventos_do_job)) is True

    eventos = recebidos()
    assert [e.tipo for e in eventos] == ["token", "message_done"]
    # O evento já chega com o id da linha gravada: a mensagem existia antes do NOTIFY.
    with conectar(banco) as conn:
        assistente = [m for m in listar_mensagens(conn, conversa_id) if m.papel == "assistente"]
        assert len(assistente) == 1
        assert assistente[0].conteudo == "olá, tudo bem?"
        assert eventos[1].dados["mensagem_id"] == assistente[0].id
        assert eventos[1].dados["conteudo"] == "olá, tudo bem?"


def test_approval_required_cria_aprovacao_pendente_e_muda_status_da_conversa(banco):
    with conectar(banco) as conn:
        conversa_id = criar_conversa(conn, "c1")
        enfileirar_mensagem(conn, conversa_id, "msg-1", "quero reembolso", "c1")
        conn.commit()

    executor = ExecutorFalso(
        [
            Evento(
                tipo="approval_required",
                dados={
                    "pedido_id": "P-1",
                    "valor": 450.0,
                    "probabilidade": 0.82,
                    "resumo": "Reembolso acima do limite",
                    "motivo_do_gate": "valor_acima_do_limite",
                },
            )
        ]
    )
    recebidos = _capturar_eventos(banco, conversa_id)
    assert _processar(banco, executor) is True

    eventos = recebidos()
    assert [e.tipo for e in eventos] == ["approval_required"]
    with conectar(banco) as conn:
        [pendente] = listar_pendentes(conn)
        assert pendente.pedido_id == "P-1"
        assert pendente.valor == 450.0
        assert pendente.motivo_do_gate == "valor_acima_do_limite"
        assert eventos[0].dados["aprovacao_id"] == pendente.id
        assert obter_conversa(conn, conversa_id).status == "aprovacao_pendente"
        assert _contar(conn, "fila_de_jobs", status="concluido") == 1


def test_executor_que_falha_marca_job_com_erro_e_publica_error(banco):
    with conectar(banco) as conn:
        conversa_id = criar_conversa(conn, "c1")
        enfileirar_mensagem(conn, conversa_id, "msg-1", "oi", "c1")
        conn.commit()

    def explode(job):
        raise RuntimeError("o grafo quebrou")

    recebidos = _capturar_eventos(banco, conversa_id)
    assert _processar(banco, ExecutorFalso(explode)) is True

    eventos = recebidos()
    assert [e.tipo for e in eventos] == ["error"]
    assert "o grafo quebrou" in eventos[0].dados["mensagem"]
    with conectar(banco) as conn:
        job = conn.execute("SELECT status, erro FROM fila_de_jobs").fetchone()
        assert job["status"] == "erro"
        assert "o grafo quebrou" in job["erro"]


def test_escutar_recebe_eventos_publicados_via_notify(banco):
    with conectar(banco) as conn:
        conversa_id = criar_conversa(conn, "c1")
        conn.commit()

    async def cenario():
        escuta = escutar(banco, conversa_id)

        async def ler():
            recebidos = []
            async for evento in escuta:
                recebidos.append(evento)
                if len(recebidos) == 2:
                    break
            await escuta.aclose()
            return recebidos

        tarefa = asyncio.create_task(ler())
        await asyncio.sleep(0.2)
        with conectar(banco, autocommit=True) as conn:
            publicar(conn, conversa_id, Evento(tipo="token", dados={"texto": "a"}))
            publicar(conn, conversa_id, Evento(tipo="token", dados={"texto": "b"}))
        return await asyncio.wait_for(tarefa, timeout=5)

    recebidos = asyncio.run(cenario())
    assert [e.dados["texto"] for e in recebidos] == ["a", "b"]
    assert canal(conversa_id) == "conversa_" + conversa_id.replace("-", "")


def test_enfileirar_avisa_os_workers_pelo_canal_da_fila(banco):
    with conectar(banco, autocommit=True) as escuta:
        escuta.execute(f"LISTEN {CANAL_DA_FILA}")
        with conectar(banco) as conn:
            enfileirar_mensagem(conn, criar_conversa(conn, "c1"), "msg-1", "oi", "c1")

        avisos = list(escuta.notifies(timeout=1.0, stop_after=1))

    assert [a.channel for a in avisos] == [CANAL_DA_FILA]


def test_worker_acorda_pelo_aviso_sem_esperar_o_intervalo(banco):
    with conectar(banco) as conn:
        conversa_id = criar_conversa(conn, "c1")
        conn.commit()
    executor = ExecutorFalso([Evento(tipo="message_done", dados={"conteudo": "oi"})])
    parar = threading.Event()
    worker = threading.Thread(
        target=rodar_worker, args=(banco, executor), kwargs={"intervalo": 30, "parar": parar}
    )
    worker.start()
    threading.Event().wait(0.3)  # o worker já está dormindo no LISTEN

    with conectar(banco) as conn:
        enfileirar_mensagem(conn, conversa_id, "msg-1", "oi", "c1")
    with conectar(banco, autocommit=True) as conn:
        for _ in range(40):
            if _contar(conn, "fila_de_jobs", status="concluido") == 1:
                break
            threading.Event().wait(0.05)
        concluidos = _contar(conn, "fila_de_jobs", status="concluido")
        parar.set()
        enfileirar_mensagem(conn, conversa_id, "msg-2", "acorda para sair", "c1")
    worker.join(timeout=5)

    assert concluidos == 1, "o job foi processado bem antes dos 30s do intervalo"


def _processar(conn_string: str, executor) -> bool:
    with conectar(conn_string, autocommit=True) as conn:
        return processar_um_job(conn, executor)


def _capturar_eventos(conn_string: str, conversa_id: str):
    """Abre uma conexão síncrona com LISTEN antes do worker rodar e devolve uma função
    que drena as notificações recebidas até então."""
    conn = conectar(conn_string, autocommit=True)
    conn.execute(f"LISTEN {canal(conversa_id)}")

    def drenar() -> list[Evento]:
        eventos = [Evento.model_validate_json(n.payload) for n in conn.notifies(timeout=1.0)]
        conn.close()
        return eventos

    return drenar
