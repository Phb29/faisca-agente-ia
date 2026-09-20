"""API HTTP: rotas de Cliente, rotas de Atendente protegidas por token, aprovação e
rejeição virando jobs de retomada, Memória Procedural e health check."""

import httpx
import pytest
from httpx import ASGITransport

from ampere.api.app import criar_app
from ampere.fila.fila import criar_aprovacao, criar_conversa, criar_ticket, gravar_mensagem
from ampere.nucleo.banco import conectar
from ampere.nucleo.config import Config

pytestmark = pytest.mark.integracao

TOKEN = "token-de-teste"
ATENDENTE = {"X-Atendente-Token": TOKEN}


class MemoriaEmDicionario:
    def __init__(self):
        self.textos: dict[str, str] = {}

    def ler(self, cliente_id: str) -> str:
        return self.textos.get(cliente_id, "")

    def escrever(self, cliente_id: str, texto: str) -> None:
        self.textos[cliente_id] = texto


@pytest.fixture
def memoria():
    return MemoriaEmDicionario()


@pytest.fixture
async def client(banco, memoria):
    app = criar_app(
        Config(database_url=banco, atendente_token=TOKEN, modelos_falsos=True),
        memoria_procedural=memoria,
        verificar_qdrant=lambda: True,
    )
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _aprovacao_pendente(banco: str) -> tuple[str, str]:
    with conectar(banco) as conn:
        conversa_id = criar_conversa(conn, "c1")
        aprovacao_id = criar_aprovacao(conn, conversa_id, "c1", "P-1", 450.0, 0.8, "resumo")
        conn.commit()
    return conversa_id, aprovacao_id


# --- Atendente ---------------------------------------------------------------------------


async def test_rotas_de_atendente_exigem_token(client):
    assert (await client.get("/atendente/aprovacoes")).status_code == 401
    errado = await client.get("/atendente/aprovacoes", headers={"X-Atendente-Token": "x"})
    assert errado.status_code == 401
    certo = await client.get("/atendente/aprovacoes", headers=ATENDENTE)
    assert certo.status_code == 200
    assert certo.json() == []


async def test_aprovar_cria_job_de_retomada_com_payload_correto(client, banco):
    conversa_id, aprovacao_id = _aprovacao_pendente(banco)

    resp = await client.post(f"/atendente/aprovacoes/{aprovacao_id}/aprovar", headers=ATENDENTE)

    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    with conectar(banco) as conn:
        job = conn.execute("SELECT * FROM fila_de_jobs WHERE id = %s", (job_id,)).fetchone()
        assert job["tipo"] == "retomada"
        assert str(job["conversa_id"]) == conversa_id
        assert job["status"] == "pendente"
        assert job["payload"] == {
            "aprovacao_id": aprovacao_id,
            "aprovado": True,
            "motivo": None,
            "cliente_id": "c1",
        }
        aprovacao = conn.execute(
            "SELECT status, decidida_em FROM aprovacoes_pendentes WHERE id = %s", (aprovacao_id,)
        ).fetchone()
        assert aprovacao["status"] == "aprovada"
        assert aprovacao["decidida_em"] is not None
    pendentes = await client.get("/atendente/aprovacoes", headers=ATENDENTE)
    assert pendentes.json() == []


async def test_rejeitar_com_motivo_grava_o_motivo(client, banco):
    _, aprovacao_id = _aprovacao_pendente(banco)

    resp = await client.post(
        f"/atendente/aprovacoes/{aprovacao_id}/rejeitar",
        headers=ATENDENTE,
        json={"motivo": "Pedido fora do prazo"},
    )

    assert resp.status_code == 200
    with conectar(banco) as conn:
        aprovacao = conn.execute(
            "SELECT status, motivo FROM aprovacoes_pendentes WHERE id = %s", (aprovacao_id,)
        ).fetchone()
        assert aprovacao["status"] == "rejeitada"
        assert aprovacao["motivo"] == "Pedido fora do prazo"
        job_id = resp.json()["job_id"]
        job = conn.execute("SELECT payload FROM fila_de_jobs WHERE id = %s", (job_id,))
        assert job.fetchone()["payload"]["aprovado"] is False
        assert job.fetchone() is None


async def test_aprovar_duas_vezes_devolve_409_e_inexistente_404(client, banco):
    _, aprovacao_id = _aprovacao_pendente(banco)
    rota = f"/atendente/aprovacoes/{aprovacao_id}/aprovar"

    assert (await client.post(rota, headers=ATENDENTE)).status_code == 200
    assert (await client.post(rota, headers=ATENDENTE)).status_code == 409
    inexistente = "00000000-0000-0000-0000-000000000000"
    resp = await client.post(f"/atendente/aprovacoes/{inexistente}/aprovar", headers=ATENDENTE)
    assert resp.status_code == 404


async def test_tickets_e_conversa_do_ticket(client, banco):
    with conectar(banco) as conn:
        conversa_id = criar_conversa(conn, "c1")
        gravar_mensagem(conn, conversa_id, "cliente", "quero falar com humano", "m1")
        gravar_mensagem(conn, conversa_id, "assistente", "encaminhando")
        ticket_id = criar_ticket(conn, conversa_id, "c1", "Quer humano", "atendimento", "alta")
        conn.commit()

    lista = await client.get("/atendente/tickets", headers=ATENDENTE)
    assert lista.status_code == 200
    assert [t["id"] for t in lista.json()] == [ticket_id]

    detalhe = await client.get(f"/atendente/tickets/{ticket_id}/conversa", headers=ATENDENTE)
    assert detalhe.status_code == 200
    assert detalhe.json()["ticket"]["resumo"] == "Quer humano"
    assert [m["conteudo"] for m in detalhe.json()["mensagens"]] == [
        "quero falar com humano",
        "encaminhando",
    ]
    inexistente = "00000000-0000-0000-0000-000000000000"
    resp = await client.get(f"/atendente/tickets/{inexistente}/conversa", headers=ATENDENTE)
    assert resp.status_code == 404


async def test_memoria_procedural_roundtrip(client, memoria):
    vazio = await client.get("/atendente/clientes/c1/memoria-procedural", headers=ATENDENTE)
    assert vazio.status_code == 200
    assert vazio.json() == {"texto": ""}

    escrito = await client.put(
        "/atendente/clientes/c1/memoria-procedural",
        headers=ATENDENTE,
        json={"texto": "Sempre tratar por 'senhor'."},
    )
    assert escrito.status_code == 200
    assert escrito.json() == {"texto": "Sempre tratar por 'senhor'."}
    assert memoria.textos["c1"] == "Sempre tratar por 'senhor'."

    lido = await client.get("/atendente/clientes/c1/memoria-procedural", headers=ATENDENTE)
    assert lido.json() == {"texto": "Sempre tratar por 'senhor'."}


async def test_memoria_procedural_sem_implementacao_devolve_503(banco):
    config = Config(database_url=banco, atendente_token=TOKEN)
    app = criar_app(config, verificar_qdrant=lambda: True)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/atendente/clientes/c1/memoria-procedural", headers=ATENDENTE)
    assert resp.status_code == 503


# --- Cliente -----------------------------------------------------------------------------


async def test_cliente_cria_e_lista_conversas(client):
    sem_header = await client.post("/conversas", json={})
    assert sem_header.status_code == 400
    vazio = await client.post("/conversas", headers={"X-Cliente-Id": "  "}, json={})
    assert vazio.status_code == 400

    criada = await client.post("/conversas", headers={"X-Cliente-Id": "c1"}, json={"titulo": "Oi"})
    assert criada.status_code == 201
    conversa_id = criada.json()["id"]

    lista = await client.get("/conversas", headers={"X-Cliente-Id": "c1"})
    assert [c["id"] for c in lista.json()] == [conversa_id]
    assert lista.json()[0]["status"] == "aberta"

    detalhe = await client.get(f"/conversas/{conversa_id}", headers={"X-Cliente-Id": "c1"})
    assert detalhe.status_code == 200
    assert detalhe.json()["titulo"] == "Oi"

    outro = await client.get(f"/conversas/{conversa_id}", headers={"X-Cliente-Id": "c2"})
    assert outro.status_code == 404
    assert (await client.get("/conversas", headers={"X-Cliente-Id": "c2"})).json() == []


async def test_enviar_mensagem_e_idempotente_por_message_id(client, banco):
    criada = await client.post("/conversas", headers={"X-Cliente-Id": "c1"}, json={})
    conversa_id = criada.json()["id"]
    corpo = {"message_id": "m-1", "conteudo": "olá"}

    primeira = await client.post(
        f"/conversas/{conversa_id}/mensagens", headers={"X-Cliente-Id": "c1"}, json=corpo
    )
    segunda = await client.post(
        f"/conversas/{conversa_id}/mensagens", headers={"X-Cliente-Id": "c1"}, json=corpo
    )

    assert primeira.status_code == 202 and primeira.json() == {"enfileirada": True}
    assert segunda.status_code == 202 and segunda.json() == {"enfileirada": False}
    mensagens = await client.get(
        f"/conversas/{conversa_id}/mensagens", headers={"X-Cliente-Id": "c1"}
    )
    assert [m["conteudo"] for m in mensagens.json()] == ["olá"]
    outro = await client.post(
        f"/conversas/{conversa_id}/mensagens", headers={"X-Cliente-Id": "c2"}, json=corpo
    )
    assert outro.status_code == 404
    with conectar(banco) as conn:
        assert conn.execute("SELECT count(*) AS n FROM fila_de_jobs").fetchone()["n"] == 1


async def test_clientes_lista_seed(client, banco):
    with conectar(banco) as conn:
        conn.execute("INSERT INTO clientes (id, nome, email) VALUES ('c1', 'Ana', 'ana@x.com')")
        conn.commit()
    resp = await client.get("/clientes")
    assert resp.status_code == 200
    assert resp.json()[0]["nome"] == "Ana"


async def test_health(client, banco):
    ok = await client.get("/health")
    assert ok.status_code == 200
    assert ok.json() == {"status": "ok", "postgres": True, "qdrant": True}

    app = criar_app(Config(database_url=banco), verificar_qdrant=lambda: False)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        falho = await c.get("/health")
    assert falho.status_code == 503
    assert falho.json()["qdrant"] is False
