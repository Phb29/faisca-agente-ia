"""API HTTP: rotas de Cliente, rotas de Atendente protegidas por token, aprovação e
rejeição virando jobs de retomada, mascaramento na borda, Memória Procedural e health check."""

import httpx
import pytest
from httpx import ASGITransport

from ampere.acoes.aprovacoes import criar_aprovacao
from ampere.acoes.ticket import ResumoDoTicket, StoreDeTicketsPostgres
from ampere.api.app import criar_app
from ampere.conversas.conversas import criar_conversa, gravar_mensagem
from ampere.nucleo.config import Config

pytestmark = pytest.mark.integracao

TOKEN = "token-de-teste"
ATENDENTE = {"X-Atendente-Token": TOKEN}
CLIENTE = {"X-Cliente-Id": "c1"}


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


def _app(banco, pool, **kwargs):
    config = Config(database_url=banco, atendente_token=TOKEN, modelos_falsos=True)
    return criar_app(
        config, pool=pool, verificar_qdrant=kwargs.pop("qdrant", lambda: True), **kwargs
    )


@pytest.fixture
async def client(banco, pool, memoria):
    app = _app(banco, pool, memoria_procedural=memoria)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _aprovacao_pendente(pool) -> tuple[str, str]:
    with pool.connection() as conn:
        conversa_id = criar_conversa(conn, "c1")
        aprovacao_id = criar_aprovacao(
            conn,
            conversa_id=conversa_id,
            cliente_id="c1",
            pedido_id="P-1",
            valor=450.0,
            probabilidade=0.8,
            resumo="resumo",
            motivo_do_gate="valor_acima_do_limite",
        )
    return conversa_id, aprovacao_id


# --- Atendente ---------------------------------------------------------------------------


async def test_rotas_de_atendente_exigem_token(client):
    assert (await client.get("/atendente/aprovacoes")).status_code == 401
    errado = await client.get("/atendente/aprovacoes", headers={"X-Atendente-Token": "x"})
    assert errado.status_code == 401
    certo = await client.get("/atendente/aprovacoes", headers=ATENDENTE)
    assert certo.status_code == 200
    assert certo.json() == []


async def test_lista_de_aprovacoes_traz_valor_numerico_e_motivo_do_gate(client, pool):
    _aprovacao_pendente(pool)

    [aprovacao] = (await client.get("/atendente/aprovacoes", headers=ATENDENTE)).json()

    assert aprovacao["valor"] == 450.0
    assert aprovacao["motivo_do_gate"] == "valor_acima_do_limite"
    assert aprovacao["status"] == "pendente"


async def test_aprovar_cria_job_de_retomada_com_payload_correto(client, pool):
    conversa_id, aprovacao_id = _aprovacao_pendente(pool)

    resp = await client.post(f"/atendente/aprovacoes/{aprovacao_id}/aprovar", headers=ATENDENTE)

    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    with pool.connection() as conn:
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


async def test_rejeitar_com_motivo_grava_o_motivo(client, pool):
    _, aprovacao_id = _aprovacao_pendente(pool)

    resp = await client.post(
        f"/atendente/aprovacoes/{aprovacao_id}/rejeitar",
        headers=ATENDENTE,
        json={"motivo": "  Pedido fora do prazo  "},
    )

    assert resp.status_code == 200
    with pool.connection() as conn:
        aprovacao = conn.execute(
            "SELECT status, motivo FROM aprovacoes_pendentes WHERE id = %s", (aprovacao_id,)
        ).fetchone()
        assert aprovacao["status"] == "rejeitada"
        assert aprovacao["motivo"] == "Pedido fora do prazo"
        job = conn.execute(
            "SELECT payload FROM fila_de_jobs WHERE id = %s", (resp.json()["job_id"],)
        ).fetchone()
        assert job["payload"]["aprovado"] is False


async def test_aprovar_duas_vezes_devolve_409_e_inexistente_404(client, pool):
    _, aprovacao_id = _aprovacao_pendente(pool)
    rota = f"/atendente/aprovacoes/{aprovacao_id}/aprovar"

    assert (await client.post(rota, headers=ATENDENTE)).status_code == 200
    assert (await client.post(rota, headers=ATENDENTE)).status_code == 409
    inexistente = "00000000-0000-0000-0000-000000000000"
    resp = await client.post(f"/atendente/aprovacoes/{inexistente}/aprovar", headers=ATENDENTE)
    assert resp.status_code == 404
    with pool.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM fila_de_jobs").fetchone()["n"] == 1


async def test_tickets_e_conversa_do_ticket(client, pool):
    with pool.connection() as conn:
        conversa_id = criar_conversa(conn, "c1")
        gravar_mensagem(conn, conversa_id, "cliente", "quero falar com humano", "m1")
        gravar_mensagem(conn, conversa_id, "assistente", "encaminhando")
    ticket = StoreDeTicketsPostgres(pool).criar(
        conversa_id,
        "c1",
        ResumoDoTicket(resumo="Quer humano", categoria="outro", prioridade="alta"),
    )

    lista = await client.get("/atendente/tickets", headers=ATENDENTE)
    assert lista.status_code == 200
    assert [t["id"] for t in lista.json()] == [ticket.id]

    detalhe = await client.get(f"/atendente/tickets/{ticket.id}/conversa", headers=ATENDENTE)
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


async def test_memoria_procedural_sem_implementacao_devolve_503(banco, pool):
    app = _app(banco, pool)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/atendente/clientes/c1/memoria-procedural", headers=ATENDENTE)
    assert resp.status_code == 503


# --- Cliente -----------------------------------------------------------------------------


async def test_cliente_cria_e_lista_conversas(client):
    sem_header = await client.post("/conversas", json={})
    assert sem_header.status_code == 400
    vazio = await client.post("/conversas", headers={"X-Cliente-Id": "  "}, json={})
    assert vazio.status_code == 400

    criada = await client.post("/conversas", headers=CLIENTE, json={"titulo": "Oi"})
    assert criada.status_code == 201
    conversa_id = criada.json()["id"]

    lista = await client.get("/conversas", headers=CLIENTE)
    assert [c["id"] for c in lista.json()] == [conversa_id]
    assert lista.json()[0]["status"] == "aberta"

    detalhe = await client.get(f"/conversas/{conversa_id}", headers=CLIENTE)
    assert detalhe.status_code == 200
    assert detalhe.json()["titulo"] == "Oi"

    outro = await client.get(f"/conversas/{conversa_id}", headers={"X-Cliente-Id": "c2"})
    assert outro.status_code == 404
    assert (await client.get("/conversas", headers={"X-Cliente-Id": "c2"})).json() == []


async def test_enviar_mensagem_e_idempotente_por_message_id(client, pool):
    conversa_id = (await client.post("/conversas", headers=CLIENTE, json={})).json()["id"]
    corpo = {"message_id": "m-1", "conteudo": "olá"}
    rota = f"/conversas/{conversa_id}/mensagens"

    primeira = await client.post(rota, headers=CLIENTE, json=corpo)
    segunda = await client.post(rota, headers=CLIENTE, json=corpo)

    assert primeira.status_code == 202
    assert primeira.json() == {"enfileirada": True, "conteudo": "olá"}
    assert segunda.status_code == 202 and segunda.json()["enfileirada"] is False
    mensagens = await client.get(rota, headers=CLIENTE)
    assert [m["conteudo"] for m in mensagens.json()] == ["olá"]
    outro = await client.post(rota, headers={"X-Cliente-Id": "c2"}, json=corpo)
    assert outro.status_code == 404
    with pool.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM fila_de_jobs").fetchone()["n"] == 1


async def test_dado_sensivel_e_mascarado_na_borda_antes_de_qualquer_gravacao(client, pool):
    conversa_id = (await client.post("/conversas", headers=CLIENTE, json={})).json()["id"]
    texto = "meu cartão é 4111 1111 1111 1111 e o cvv 123"

    resp = await client.post(
        f"/conversas/{conversa_id}/mensagens",
        headers=CLIENTE,
        json={"message_id": "m-1", "conteudo": texto},
    )

    assert resp.json()["conteudo"] == "meu cartão é [CARTÃO MASCARADO] e o cvv [CVV MASCARADO]"
    with pool.connection() as conn:
        transcript = conn.execute("SELECT conteudo FROM mensagens").fetchone()["conteudo"]
        job = conn.execute("SELECT payload FROM fila_de_jobs").fetchone()["payload"]
        titulo = conn.execute("SELECT titulo FROM conversas").fetchone()["titulo"]
    for gravado in (transcript, job["conteudo"], titulo):
        assert "4111" not in gravado and "123" not in gravado


async def test_primeira_mensagem_vira_o_titulo_da_conversa(client):
    conversa_id = (await client.post("/conversas", headers=CLIENTE, json={})).json()["id"]
    rota = f"/conversas/{conversa_id}/mensagens"

    await client.post(
        rota, headers=CLIENTE, json={"message_id": "a", "conteudo": "Qual a garantia?"}
    )
    await client.post(rota, headers=CLIENTE, json={"message_id": "b", "conteudo": "E o frete?"})

    detalhe = await client.get(f"/conversas/{conversa_id}", headers=CLIENTE)
    assert detalhe.json()["titulo"] == "Qual a garantia?"


async def test_conversa_esperando_o_atendente_nao_aceita_mensagem_nova(client, pool):
    conversa_id = (await client.post("/conversas", headers=CLIENTE, json={})).json()["id"]
    with pool.connection() as conn:
        conn.execute(
            "UPDATE conversas SET status = 'aprovacao_pendente' WHERE id = %s", (conversa_id,)
        )

    resp = await client.post(
        f"/conversas/{conversa_id}/mensagens",
        headers=CLIENTE,
        json={"message_id": "m-1", "conteudo": "e aí?"},
    )

    assert resp.status_code == 409
    with pool.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM fila_de_jobs").fetchone()["n"] == 0


async def test_mensagem_vazia_e_rejeitada(client):
    conversa_id = (await client.post("/conversas", headers=CLIENTE, json={})).json()["id"]

    resp = await client.post(
        f"/conversas/{conversa_id}/mensagens",
        headers=CLIENTE,
        json={"message_id": "m-1", "conteudo": ""},
    )

    assert resp.status_code == 422


async def test_clientes_e_pedidos_do_cliente(client, pool):
    with pool.connection() as conn:
        conn.execute("INSERT INTO clientes (id, nome, email) VALUES ('c1', 'Ana', 'ana@x.com')")
        conn.execute(
            "INSERT INTO pedidos (id, cliente_id, produto, linha, valor, status, data) VALUES "
            "('P1', 'c1', 'Fone', 'acessorios', 199.90, 'entregue', '2026-08-01')"
        )

    clientes = await client.get("/clientes")
    pedidos = await client.get("/pedidos", headers=CLIENTE)
    de_outro = await client.get("/pedidos", headers={"X-Cliente-Id": "c2"})

    assert clientes.json() == [{"id": "c1", "nome": "Ana", "email": "ana@x.com"}]
    assert pedidos.json() == [
        {
            "id": "P1",
            "cliente_id": "c1",
            "produto": "Fone",
            "linha": "acessorios",
            "valor": 199.9,
            "status": "entregue",
            "data": "2026-08-01",
        }
    ]
    assert de_outro.json() == []


async def test_health(client, banco, pool):
    ok = await client.get("/health")
    assert ok.status_code == 200
    assert ok.json() == {"status": "ok", "postgres": True, "qdrant": True}

    app = _app(banco, pool, qdrant=lambda: False)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        falho = await c.get("/health")
    assert falho.status_code == 503
    assert falho.json()["qdrant"] is False
