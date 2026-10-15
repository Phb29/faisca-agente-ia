"""Rotas da Tela de Avaliação: token, listas, amostra (202 e 409), liberação das abandonadas
e o stream de uma amostra."""

import httpx
import pytest
from httpx import ASGITransport

from ampere.api.app import criar_app
from ampere.evals.execucoes import (
    canal_da_execucao,
    criar_amostra,
    marcar_rodando,
    salvar_completa,
)
from ampere.nucleo.banco import conectar
from ampere.nucleo.config import Config

pytestmark = pytest.mark.integracao

TOKEN = "token-de-teste"
ATENDENTE = {"X-Atendente-Token": TOKEN}
NENHUMA = "00000000-0000-0000-0000-000000000000"


def _app(banco, pool):
    config = Config(database_url=banco, atendente_token=TOKEN, modelos_falsos=True)
    return criar_app(config, pool=pool, verificar_qdrant=lambda: True)


@pytest.fixture
async def client(banco, pool):
    transporte = ASGITransport(app=_app(banco, pool))
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as c:
        yield c


async def test_tudo_exige_o_token_do_atendente(client):
    for rota in (
        "/avaliacao/amostra",
        "/avaliacao/rag/execucoes",
        f"/avaliacao/execucoes/{NENHUMA}",
        f"/avaliacao/execucoes/{NENHUMA}/stream",
    ):
        assert (await client.get(rota)).status_code == 401, rota
    assert (await client.post("/avaliacao/rag/amostra")).status_code == 401


async def test_lista_as_execucoes_do_eval_sem_os_casos(client, banco):
    with conectar(banco, autocommit=True) as conn:
        execucao_id = salvar_completa(
            conn, "agente", contexto={}, resumo={"tudo": 1.0}, casos=[{"id": "ag01"}]
        )

    resp = await client.get("/avaliacao/agente/execucoes", headers=ATENDENTE)
    inteira = await client.get(f"/avaliacao/execucoes/{execucao_id}", headers=ATENDENTE)

    assert resp.status_code == 200
    [execucao] = resp.json()
    assert execucao["id"] == execucao_id
    assert "casos" not in execucao
    assert inteira.json()["casos"] == [{"id": "ag01"}]
    assert (await client.get("/avaliacao/rag/execucoes", headers=ATENDENTE)).json() == []


async def test_eval_invalido_e_execucao_inexistente_sao_404(client):
    assert (await client.get("/avaliacao/nada/execucoes", headers=ATENDENTE)).status_code == 404
    assert (await client.post("/avaliacao/nada/amostra", headers=ATENDENTE)).status_code == 404
    malformado = await client.get("/avaliacao/execucoes/nao-e-uuid", headers=ATENDENTE)
    assert malformado.status_code == 404
    inexistente = await client.get(f"/avaliacao/execucoes/{NENHUMA}", headers=ATENDENTE)
    assert inexistente.status_code == 404


async def test_amostra_cria_execucao_e_job_juntos(client, banco):
    resp = await client.post("/avaliacao/juiz/amostra", headers=ATENDENTE)

    assert resp.status_code == 202
    execucao_id = resp.json()["execucao_id"]
    with conectar(banco, autocommit=True) as conn:
        job = conn.execute("SELECT tipo, conversa_id, canal, payload FROM fila_de_jobs").fetchone()
    assert job["tipo"] == "eval"
    assert job["conversa_id"] is None
    assert job["canal"] == canal_da_execucao(execucao_id)
    assert job["payload"] == {"execucao_id": execucao_id, "eval": "juiz"}
    atual = (await client.get("/avaliacao/amostra", headers=ATENDENTE)).json()
    assert atual["id"] == execucao_id
    assert atual["status"] == "pendente"
    assert "casos" not in atual


async def test_segunda_amostra_de_qualquer_eval_recebe_409_com_a_primeira(client, banco):
    primeira = (await client.post("/avaliacao/rag/amostra", headers=ATENDENTE)).json()

    resp = await client.post("/avaliacao/agente/amostra", headers=ATENDENTE)

    assert resp.status_code == 409
    assert resp.json()["execucao_id"] == primeira["execucao_id"]
    assert resp.json()["eval"] == "rag"
    with conectar(banco, autocommit=True) as conn:
        assert conn.execute("SELECT count(*) AS n FROM fila_de_jobs").fetchone()["n"] == 1


async def test_sem_amostra_em_andamento_a_rota_devolve_null(client):
    resp = await client.get("/avaliacao/amostra", headers=ATENDENTE)

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

    resp = await client.post("/avaliacao/agente/amostra", headers=ATENDENTE)

    assert resp.status_code == 202
    lida = (await client.get(f"/avaliacao/execucoes/{velha}", headers=ATENDENTE)).json()
    assert lida["status"] == "erro"
    assert lida["erro"] == "tempo esgotado"
    atual = (await client.get("/avaliacao/amostra", headers=ATENDENTE)).json()
    assert atual["id"] == resp.json()["execucao_id"]
