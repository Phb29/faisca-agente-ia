"""Rotas da Tela de Avaliação, com uma sessão aberta: listas, amostra (202 e 409), liberação
das abandonadas e o stream de uma amostra. A exigência da sessão é testada em
`test_acesso.py`."""

import asyncio
import random
import threading

import httpx
import pytest
from httpx import ASGITransport

from ampere.api.app import criar_app
from ampere.evals.ao_vivo import ExecutorDeAvaliacao
from ampere.evals.execucoes import (
    RegistroPostgres,
    anexar_caso,
    canal_da_execucao,
    criar_amostra,
    marcar_rodando,
    obter,
    salvar_completa,
)
from ampere.fila.eventos import Evento, publicar
from ampere.fila.executor import ExecutorPorTipo
from ampere.fila.worker import processar_um_job
from ampere.nucleo.banco import conectar
from ampere.nucleo.config import Config
from tests.apoio import composicao_falsa
from tests.integracao.apoio_sse import coletar_ate, eventos_sse, servidor_no_ar

pytestmark = pytest.mark.integracao

NENHUMA = "00000000-0000-0000-0000-000000000000"


def _app(banco, pool):
    config = Config(database_url=banco, modelos_falsos=True)
    return criar_app(config, pool=pool, verificar_qdrant=lambda: True)


@pytest.fixture
async def client(banco, pool, sessao):
    transporte = ASGITransport(app=_app(banco, pool))
    async with httpx.AsyncClient(transport=transporte, base_url="http://test", headers=sessao) as c:
        yield c


async def test_lista_as_execucoes_do_eval_sem_os_casos(client, banco):
    with conectar(banco, autocommit=True) as conn:
        execucao_id = salvar_completa(
            conn, "agente", contexto={}, resumo={"tudo": 1.0}, casos=[{"id": "ag01"}]
        )

    resp = await client.get("/avaliacao/agente/execucoes")
    inteira = await client.get(f"/avaliacao/execucoes/{execucao_id}")

    assert resp.status_code == 200
    [execucao] = resp.json()
    assert execucao["id"] == execucao_id
    assert "casos" not in execucao
    assert inteira.json()["casos"] == [{"id": "ag01"}]
    assert (await client.get("/avaliacao/rag/execucoes")).json() == []


async def test_lista_vem_das_mais_novas_para_as_mais_velhas_ate_o_limite(client, banco):
    with conectar(banco, autocommit=True) as conn:
        velha = salvar_completa(conn, "juiz", contexto={}, resumo={}, casos=[])
        conn.execute(
            "UPDATE execucoes_de_eval SET criada_em = now() - interval '1 day' WHERE id = %s",
            (velha,),
        )
        nova = salvar_completa(conn, "juiz", contexto={}, resumo={}, casos=[])

    todas = await client.get("/avaliacao/juiz/execucoes")
    uma = await client.get("/avaliacao/juiz/execucoes?limite=1")

    assert [e["id"] for e in todas.json()] == [nova, velha]
    assert [e["id"] for e in uma.json()] == [nova]


async def test_eval_invalido_e_execucao_inexistente_sao_404(client):
    assert (await client.get("/avaliacao/nada/execucoes")).status_code == 404
    assert (await client.post("/avaliacao/nada/amostra")).status_code == 404
    malformado = await client.get("/avaliacao/execucoes/nao-e-uuid")
    assert malformado.status_code == 404
    inexistente = await client.get(f"/avaliacao/execucoes/{NENHUMA}")
    assert inexistente.status_code == 404
    # O stream responde 404 antes de abrir, e fecha a escuta que já tinha aberto.
    for execucao_id in ("nao-e-uuid", NENHUMA):
        stream = await client.get(f"/avaliacao/execucoes/{execucao_id}/stream")
        assert stream.status_code == 404, execucao_id


async def test_amostra_cria_execucao_e_job_juntos(client, banco):
    resp = await client.post("/avaliacao/juiz/amostra")

    assert resp.status_code == 202
    execucao_id = resp.json()["execucao_id"]
    with conectar(banco, autocommit=True) as conn:
        job = conn.execute("SELECT tipo, conversa_id, canal, payload FROM fila_de_jobs").fetchone()
    assert job["tipo"] == "eval"
    assert job["conversa_id"] is None
    assert job["canal"] == canal_da_execucao(execucao_id)
    assert job["payload"] == {"execucao_id": execucao_id, "eval": "juiz"}
    atual = (await client.get("/avaliacao/amostra")).json()
    assert atual["id"] == execucao_id
    assert atual["status"] == "pendente"
    assert "casos" not in atual


async def test_segunda_amostra_de_qualquer_eval_recebe_409_com_a_primeira(client, banco):
    primeira = (await client.post("/avaliacao/rag/amostra")).json()

    resp = await client.post("/avaliacao/agente/amostra")

    assert resp.status_code == 409
    assert resp.json()["execucao_id"] == primeira["execucao_id"]
    assert resp.json()["eval"] == "rag"
    with conectar(banco, autocommit=True) as conn:
        assert conn.execute("SELECT count(*) AS n FROM fila_de_jobs").fetchone()["n"] == 1


async def test_sem_amostra_em_andamento_a_rota_devolve_null(client):
    resp = await client.get("/avaliacao/amostra")

    assert resp.status_code == 200
    assert resp.json() is None


async def test_amostra_abandonada_e_liberada_na_hora_de_criar_outra(client, banco):
    with conectar(banco, autocommit=True) as conn:
        velha = criar_amostra(conn, "agente")
        marcar_rodando(conn, velha, {})
        conn.execute(
            "UPDATE execucoes_de_eval SET iniciada_em = now() - interval '6 minutes' WHERE id = %s",
            (velha,),
        )

    resp = await client.post("/avaliacao/agente/amostra")

    assert resp.status_code == 202
    lida = (await client.get(f"/avaliacao/execucoes/{velha}")).json()
    assert lida["status"] == "erro"
    assert lida["erro"] == "tempo esgotado"
    atual = (await client.get("/avaliacao/amostra")).json()
    assert atual["id"] == resp.json()["execucao_id"]


# --- stream -----------------------------------------------------------------------------------


@pytest.fixture
def servidor(banco, pool):
    with servidor_no_ar(_app(banco, pool)) as url:
        yield url


def _processar_um(banco: str, executor) -> None:
    with conectar(banco, autocommit=True) as conn:
        processar_um_job(conn, executor)


async def test_amostra_de_ponta_a_ponta_pela_fila_e_pelo_stream(servidor, banco, pool, sessao):
    """A API cria a amostra, um worker com o executor de verdade (modelos falsos) roda o job,
    e o stream entrega a foto, o começo, as fases, os casos e o fim."""
    executor = ExecutorPorTipo(
        {
            "eval": ExecutorDeAvaliacao(
                Config(modelos_falsos=True),
                composicao_falsa(),
                RegistroPostgres(pool),
                sorteio=lambda: random.Random(3),
            )
        }
    )
    async with httpx.AsyncClient(base_url=servidor, timeout=20, headers=sessao) as client:
        criada = await client.post("/avaliacao/juiz/amostra")
        execucao_id = criada.json()["execucao_id"]
        rota = f"/avaliacao/execucoes/{execucao_id}/stream"
        async with client.stream("GET", rota) as r:
            assert r.status_code == 200
            thread = threading.Thread(target=_processar_um, args=(banco, executor))
            thread.start()
            recebidos = await asyncio.wait_for(coletar_ate(r, {"eval_fim", "error"}), timeout=20)
            thread.join(timeout=10)
            assert not thread.is_alive(), "o worker não terminou o job"

    tipos = [t for t, _ in recebidos]
    assert tipos[0] == "eval_estado"
    assert recebidos[0][1]["status"] == "pendente"
    assert tipos[1] == "eval_inicio"
    assert tipos.count("eval_fase") == 3
    assert tipos.count("eval_caso") == 3
    assert tipos[-1] == "eval_fim"
    with conectar(banco, autocommit=True) as conn:
        lida = obter(conn, execucao_id)
    assert lida["status"] == "concluida"
    assert len(lida["casos"]) == 3


async def test_stream_de_execucao_terminada_manda_so_a_foto_e_fecha(servidor, banco, sessao):
    with conectar(banco, autocommit=True) as conn:
        execucao_id = salvar_completa(
            conn, "rag", contexto={}, resumo={"n": 1}, casos=[{"id": "rag-001"}]
        )

    async with httpx.AsyncClient(base_url=servidor, timeout=10, headers=sessao) as client:
        rota = f"/avaliacao/execucoes/{execucao_id}/stream"
        async with client.stream("GET", rota) as r:
            recebidos = await asyncio.wait_for(coletar_ate(r, set()), timeout=10)

    assert [t for t, _ in recebidos] == ["eval_estado"]
    assert recebidos[0][1]["casos"] == [{"id": "rag-001"}]


async def test_stream_no_meio_da_amostra_repoe_os_casos_prontos(servidor, banco, sessao):
    """É o F5 no meio da aula: a foto traz o que já terminou, e o resto chega pelo canal."""
    with conectar(banco, autocommit=True) as conn:
        execucao_id = criar_amostra(conn, "agente")
        marcar_rodando(
            conn, execucao_id, {"sorteados": [{"id": "ag01", "texto": "t", "grupo": "duvida"}]}
        )
        anexar_caso(conn, execucao_id, {"id": "ag01"})

    async with httpx.AsyncClient(base_url=servidor, timeout=10, headers=sessao) as client:
        rota = f"/avaliacao/execucoes/{execucao_id}/stream"
        async with client.stream("GET", rota) as r:
            eventos = eventos_sse(r)
            foto = await asyncio.wait_for(anext(eventos), timeout=10)
            with conectar(banco, autocommit=True) as conn:
                fim = Evento(tipo="eval_fim", dados={"resumo": {"n": 1}})
                publicar(conn, canal_da_execucao(execucao_id), fim)
            depois = await asyncio.wait_for(anext(eventos), timeout=10)

    assert foto[0] == "eval_estado"
    assert foto[1]["status"] == "rodando"
    assert foto[1]["casos"] == [{"id": "ag01"}]
    assert foto[1]["contexto"]["sorteados"][0]["id"] == "ag01"
    assert depois == ("eval_fim", {"resumo": {"n": 1}})
