"""SSE de ponta a ponta: um worker de teste publica por NOTIFY, a API escuta por LISTEN
e o front recebe os eventos; a reconexão devolve a última mensagem gravada.

O `ASGITransport` do httpx só devolve a resposta quando o app termina, o que nunca acontece
num stream aberto; por isso o teste sobe um uvicorn de verdade numa thread.
"""

import asyncio
import threading

import httpx
import pytest

from ampere.api.app import criar_app
from ampere.fila.eventos import Evento
from ampere.fila.executor import ExecutorFalso
from ampere.fila.worker import processar_um_job
from ampere.nucleo.banco import conectar
from ampere.nucleo.config import Config
from tests.integracao.apoio_sse import coletar, servidor_no_ar

pytestmark = pytest.mark.integracao

CLIENTE = {"X-Cliente-Id": "c1"}


@pytest.fixture
def servidor(banco, pool):
    config = Config(database_url=banco, modelos_falsos=True)
    app = criar_app(config, pool=pool, verificar_qdrant=lambda: True)
    with servidor_no_ar(app) as url:
        yield url


def _processar_um(banco: str, executor: ExecutorFalso) -> None:
    with conectar(banco, autocommit=True) as conn:
        processar_um_job(conn, executor)


EVENTOS_DO_PRIMEIRO_JOB = [
    Evento(tipo="token", dados={"texto": "Olá"}),
    Evento(tipo="tool_call", dados={"nome": "consultar_pedido", "args": {"pedido_id": "P-1"}}),
    Evento(
        tipo="approval_required",
        dados={
            "pedido_id": "P-1",
            "valor": 450.0,
            "probabilidade": 0.9,
            "resumo": "Acima",
            "motivo_do_gate": "valor_acima_do_limite",
        },
    ),
    Evento(tipo="message_done", dados={"conteudo": "Olá, seu reembolso aguarda aprovação."}),
]


def _executor_de_teste() -> ExecutorFalso:
    def eventos(job):
        if job.message_id == "m-2":
            raise RuntimeError("falha simulada")
        return EVENTOS_DO_PRIMEIRO_JOB

    return ExecutorFalso(eventos)


async def test_sse_recebe_os_cinco_eventos_na_ordem_e_reenvia_ao_reconectar(
    servidor, banco, sessao
):
    async with httpx.AsyncClient(base_url=servidor, timeout=10, headers=sessao) as client:
        criada = await client.post("/conversas", headers=CLIENTE, json={})
        conversa_id = criada.json()["id"]
        for message_id in ("m-1", "m-2"):
            resp = await client.post(
                f"/conversas/{conversa_id}/mensagens",
                headers=CLIENTE,
                json={"message_id": message_id, "conteudo": "quero reembolso"},
            )
            assert resp.status_code == 202

        async with client.stream("GET", f"/conversas/{conversa_id}/stream", headers=CLIENTE) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")

            def worker():
                executor = _executor_de_teste()
                with conectar(banco, autocommit=True) as conn:
                    assert processar_um_job(conn, executor) is True
                    assert processar_um_job(conn, executor) is True

            thread = threading.Thread(target=worker)
            thread.start()
            recebidos = await asyncio.wait_for(coletar(r, 5), timeout=10)
            thread.join(timeout=5)
            assert not thread.is_alive(), "o worker não terminou o job"

        tipos = [t for t, _ in recebidos]
        assert tipos == ["token", "tool_call", "approval_required", "message_done", "error"]
        assert recebidos[0][1] == {"texto": "Olá"}
        assert recebidos[1][1]["nome"] == "consultar_pedido"
        assert "aprovacao_id" in recebidos[2][1]
        assert recebidos[3][1]["conteudo"] == "Olá, seu reembolso aguarda aprovação."
        assert recebidos[3][1]["mensagem_id"]
        assert "reenvio" not in recebidos[3][1]
        assert "falha simulada" in recebidos[4][1]["mensagem"]

        # Reconexão: a última mensagem gravada do assistente volta como message_done.
        async with client.stream("GET", f"/conversas/{conversa_id}/stream", headers=CLIENTE) as r:
            reenviados = await asyncio.wait_for(coletar(r, 1), timeout=10)
        assert reenviados[0][0] == "message_done"
        assert reenviados[0][1]["reenvio"] is True
        assert reenviados[0][1]["mensagem_id"] == recebidos[3][1]["mensagem_id"]
        assert reenviados[0][1]["conteudo"] == "Olá, seu reembolso aguarda aprovação."

        # Conversa de outro Cliente não pode ser escutada.
        outro = await client.get(f"/conversas/{conversa_id}/stream", headers={"X-Cliente-Id": "c2"})
        assert outro.status_code == 404


async def test_sse_de_conversa_nova_manda_o_primeiro_byte_na_hora(servidor, sessao):
    """Conversa nova não tem resposta para reenviar. Sem um primeiro byte, o BFF do Next só
    manda os cabeçalhos junto com o ping de 15 s, e o front espera esse tempo todo para
    considerar o stream aberto e postar a primeira mensagem."""
    async with httpx.AsyncClient(base_url=servidor, timeout=10, headers=sessao) as client:
        criada = await client.post("/conversas", headers=CLIENTE, json={})
        conversa_id = criada.json()["id"]

        async with client.stream("GET", f"/conversas/{conversa_id}/stream", headers=CLIENTE) as r:
            assert r.status_code == 200
            bytes_ = r.aiter_raw()
            primeiro = await asyncio.wait_for(anext(bytes_), timeout=2)

    # Um comentário SSE: o EventSource ignora, e nenhum evento falso chega ao front.
    assert primeiro.startswith(b":")
    assert b"ping" not in primeiro


async def test_sse_aceita_cliente_id_por_query_string(servidor, banco, sessao):
    """O EventSource do navegador não envia headers; a query string faz as vezes dele."""
    async with httpx.AsyncClient(base_url=servidor, timeout=10, headers=sessao) as client:
        criada = await client.post("/conversas", headers=CLIENTE, json={})
        conversa_id = criada.json()["id"]
        resp = await client.post(
            f"/conversas/{conversa_id}/mensagens",
            headers=CLIENTE,
            json={"message_id": "m-1", "conteudo": "oi"},
        )
        assert resp.status_code == 202

        rota = f"/conversas/{conversa_id}/stream?cliente_id=c1"
        async with client.stream("GET", rota) as r:
            assert r.status_code == 200
            executor = ExecutorFalso([Evento(tipo="message_done", dados={"conteudo": "olá"})])
            thread = threading.Thread(target=_processar_um, args=(banco, executor))
            thread.start()
            recebidos = await asyncio.wait_for(coletar(r, 1), timeout=10)
            thread.join(timeout=5)
            assert not thread.is_alive(), "o worker não terminou o job"
        assert recebidos[0][0] == "message_done"
        assert recebidos[0][1]["conteudo"] == "olá"

        sem_nada = await client.get(f"/conversas/{conversa_id}/stream")
        assert sem_nada.status_code == 400
        outro = await client.get(f"/conversas/{conversa_id}/stream?cliente_id=c2")
        assert outro.status_code == 404
