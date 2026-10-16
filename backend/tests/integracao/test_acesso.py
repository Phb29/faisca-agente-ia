"""Acesso: sessões e limite de tentativas no Postgres, as rotas de login e a sessão exigida em
todas as outras rotas, menos `/health` e `/acesso/entrar`."""

import asyncio
import hashlib
import logging
import threading
import time

import httpx
import pytest
from httpx import ASGITransport
from psycopg_pool import PoolTimeout

from ampere.acesso.senha import gerar_hash
from ampere.acesso.sessoes import (
    criar_sessao,
    encerrar_sessao,
    limpar_expiradas,
    sessao_valida,
)
from ampere.acesso.tentativas import Bloqueado, comecar, limpar_antigas, marcar_sucesso
from ampere.api import acesso as rotas_de_acesso
from ampere.api.app import criar_app
from ampere.nucleo.config import Config

pytestmark = pytest.mark.integracao

EMAIL = "dono@exemplo.com.br"
SENHA = "uma senha forte de teste"
HASH = gerar_hash(SENHA)
IP = {"X-Ip-Do-Cliente": "203.0.113.7"}
NENHUMA = "00000000-0000-0000-0000-000000000000"
FALHOU = {"detail": "E-mail ou senha incorretos."}
SEM_SESSAO = {"detail": "Sessão inválida ou expirada."}
ABERTAS = {("GET", "/health"), ("POST", "/acesso/entrar"), ("POST", "/acesso/sair")}


def _falhas(conn, quantas: int, *, email=EMAIL, ip="10.0.0.1", ha_minutos: float = 0) -> None:
    for _ in range(quantas):
        conn.execute(
            "INSERT INTO tentativas_de_login (email, ip, sucesso, momento) "
            "VALUES (%s, %s, false, now() - make_interval(secs => %s))",
            (email, ip, ha_minutos * 60),
        )


def _contar_em(conn, onde: str = "true") -> int:
    linha = conn.execute(f"SELECT count(*) AS n FROM tentativas_de_login WHERE {onde}").fetchone()
    return linha["n"]


# --- sessões ----------------------------------------------------------------------------


def test_sessao_criada_vale_e_so_o_hash_do_token_fica_no_banco(pool):
    with pool.connection() as conn:
        token, expira_em = criar_sessao(conn, EMAIL, horas=12, ip="10.0.0.1", user_agent="ua")
        gravada = conn.execute("SELECT *, now() AS agora FROM sessoes").fetchone()
        sessao = sessao_valida(conn, token)

    assert len(token) >= 40
    assert gravada["id"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(gravada)
    assert (gravada["ip"], gravada["user_agent"]) == ("10.0.0.1", "ua")
    assert expira_em == gravada["expira_em"]
    assert 11.9 * 3600 < (expira_em - gravada["agora"]).total_seconds() <= 12 * 3600
    assert sessao.email == EMAIL
    assert sessao.expira_em == expira_em


def test_token_desconhecido_ou_vazio_nao_vale(pool):
    with pool.connection() as conn:
        criar_sessao(conn, EMAIL, horas=12, ip="10.0.0.1", user_agent="ua")

        assert sessao_valida(conn, "token-inventado") is None
        assert sessao_valida(conn, "") is None


def test_sessao_expirada_nao_vale_e_e_limpa(pool):
    with pool.connection() as conn:
        velho, _ = criar_sessao(conn, EMAIL, horas=12, ip="10.0.0.1", user_agent="ua")
        novo, _ = criar_sessao(conn, EMAIL, horas=12, ip="10.0.0.1", user_agent="ua")
        conn.execute(
            "UPDATE sessoes SET expira_em = now() - interval '1 second' WHERE id = %s",
            (hashlib.sha256(velho.encode()).hexdigest(),),
        )

        assert sessao_valida(conn, velho) is None
        assert limpar_expiradas(conn) == 1
        assert conn.execute("SELECT count(*) AS n FROM sessoes").fetchone()["n"] == 1
        assert sessao_valida(conn, novo) is not None


def test_encerrar_derruba_a_sessao_e_pode_repetir(pool):
    with pool.connection() as conn:
        token, _ = criar_sessao(conn, EMAIL, horas=12, ip="10.0.0.1", user_agent="ua")

        encerrar_sessao(conn, token)
        encerrar_sessao(conn, token)

        assert sessao_valida(conn, token) is None


# --- tentativas -------------------------------------------------------------------------


def test_tentativa_comeca_como_falha_e_vira_sucesso_quando_a_senha_bate(pool):
    with pool.connection() as conn:
        errada = comecar(conn, "  dono@exemplo.com.br ", "10.0.0.1")
        certa = comecar(conn, EMAIL, "10.0.0.1")
        marcar_sucesso(conn, certa)
        linhas = conn.execute(
            "SELECT id, email, ip, sucesso FROM tentativas_de_login ORDER BY id"
        ).fetchall()

    assert linhas == [
        {"id": errada, "email": EMAIL, "ip": "10.0.0.1", "sucesso": False},
        {"id": certa, "email": EMAIL, "ip": "10.0.0.1", "sucesso": True},
    ]


def test_cinco_falhas_do_mesmo_ip_bloqueiam_ate_a_mais_antiga_sair_da_janela(pool):
    with pool.connection() as conn:
        _falhas(conn, 3, ip="10.0.0.1")
        _falhas(conn, 1, ip="10.0.0.1", ha_minutos=10)
        comecar(conn, EMAIL, "10.0.0.1")  # a quinta ainda cabe

        with pytest.raises(Bloqueado) as bloqueado:
            comecar(conn, EMAIL, "10.0.0.1")

        assert 290 <= bloqueado.value.segundos <= 300
        assert _contar_em(conn, "ip = '10.0.0.1'") == 5  # a bloqueada não deixa rastro
        comecar(conn, "outro@x.com", "10.0.0.2")


def test_falhas_com_mais_de_15_minutos_e_sucessos_nao_contam(pool):
    with pool.connection() as conn:
        _falhas(conn, 10, ip="10.0.0.1", ha_minutos=16)
        for _ in range(10):
            marcar_sucesso(conn, comecar(conn, EMAIL, "10.0.0.1"))
        _falhas(conn, 4, ip="10.0.0.1")

        comecar(conn, EMAIL, "10.0.0.1")  # a quinta falha da janela ainda cabe


def test_vinte_falhas_do_mesmo_email_bloqueiam_de_qualquer_ip(pool):
    with pool.connection() as conn:
        for i in range(19):
            comecar(conn, EMAIL, f"10.0.1.{i}")
        comecar(conn, "  dono@exemplo.com.br ", "10.0.1.99")  # a vigésima ainda cabe

        with pytest.raises(Bloqueado) as bloqueado:
            comecar(conn, " dono@exemplo.com.br", "10.0.2.1")

        assert 890 <= bloqueado.value.segundos <= 900
        comecar(conn, "outro@x.com", "10.0.2.1")


def test_limpar_antigas_apaga_so_o_que_passou_de_um_dia(pool):
    with pool.connection() as conn:
        _falhas(conn, 3, ha_minutos=25 * 60)
        _falhas(conn, 2, ha_minutos=23 * 60)

        assert limpar_antigas(conn) == 3
        restantes = conn.execute("SELECT count(*) AS n FROM tentativas_de_login").fetchone()
        assert restantes["n"] == 2


# --- rotas ------------------------------------------------------------------------------


def _app(banco, pool, **login):
    login = login or {"login_email": "dono@exemplo.com.br", "login_senha_hash": HASH}
    config = Config(database_url=banco, modelos_falsos=True, **login)
    return criar_app(config, pool=pool, verificar_qdrant=lambda: True)


def _cliente(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client(banco, pool):
    async with _cliente(_app(banco, pool)) as c:
        yield c


async def _entrar(client, email=EMAIL, senha=SENHA, headers=IP) -> httpx.Response:
    return await client.post(
        "/acesso/entrar", json={"email": email, "senha": senha}, headers=headers
    )


def _contar(pool, tabela: str, onde: str = "true") -> int:
    with pool.connection() as conn:
        return conn.execute(f"SELECT count(*) AS n FROM {tabela} WHERE {onde}").fetchone()["n"]


async def test_login_certo_devolve_token_e_cria_sessao(client, pool):
    resp = await _entrar(client, email="  dono@exemplo.com.br ")

    assert resp.status_code == 200
    corpo = resp.json()
    assert set(corpo) == {"token", "email", "expira_em"}
    assert corpo["email"] == EMAIL
    with pool.connection() as conn:
        sessao = conn.execute("SELECT ip, user_agent FROM sessoes").fetchone()
        tentativa = conn.execute("SELECT email, ip, sucesso FROM tentativas_de_login").fetchone()
    assert sessao["ip"] == "203.0.113.7"
    assert tentativa == {"email": EMAIL, "ip": "203.0.113.7", "sucesso": True}

    eu = await client.get("/acesso/eu", headers={"Authorization": f"Bearer {corpo['token']}"})
    assert eu.status_code == 200
    assert eu.json() == {"email": EMAIL, "expira_em": corpo["expira_em"]}


async def test_senha_errada_e_email_errado_dao_o_mesmo_401(client, pool):
    senha_errada = await _entrar(client, senha="outra senha")
    email_errado = await _entrar(client, email="alguem@exemplo.com.br")

    assert senha_errada.status_code == email_errado.status_code == 401
    assert senha_errada.json() == email_errado.json() == FALHOU
    assert _contar(pool, "sessoes") == 0
    assert _contar(pool, "tentativas_de_login", "NOT sucesso") == 2


async def test_sexta_tentativa_do_mesmo_ip_na_janela_da_429_com_retry_after(client, pool):
    for _ in range(5):
        assert (await _entrar(client, senha="chute")).status_code == 401

    bloqueado = await _entrar(client)  # nem a senha certa passa

    assert bloqueado.status_code == 429
    assert 890 <= int(bloqueado.headers["Retry-After"]) <= 900
    assert bloqueado.json() == {"detail": "Muitas tentativas. Tente de novo em 15 minutos."}
    assert _contar(pool, "tentativas_de_login") == 5  # o 429 não registra tentativa
    assert _contar(pool, "sessoes") == 0
    outro_ip = await _entrar(client, headers={"X-Ip-Do-Cliente": "198.51.100.1"})
    assert outro_ip.status_code == 200


async def test_falhas_com_mais_de_15_minutos_nao_contam(client, pool):
    with pool.connection() as conn:
        _falhas(conn, 5, ip="203.0.113.7", ha_minutos=16)

    assert (await _entrar(client)).status_code == 200


async def test_sem_o_cabecalho_o_ip_e_o_da_conexao(client, pool):
    await _entrar(client, senha="chute", headers={})

    with pool.connection() as conn:
        tentativa = conn.execute("SELECT ip FROM tentativas_de_login").fetchone()
    assert tentativa["ip"] == "127.0.0.1"


async def test_so_o_login_certo_limpa_sessoes_expiradas_e_tentativas_antigas(client, pool):
    """Limpar custa uma varredura; o login certo é raro, a tentativa errada não."""
    with pool.connection() as conn:
        criar_sessao(conn, EMAIL, horas=1, ip="10.0.0.1", user_agent="ua")
        conn.execute("UPDATE sessoes SET expira_em = now() - interval '1 minute'")
        _falhas(conn, 3, ip="10.0.0.1", ha_minutos=2 * 24 * 60)

    await _entrar(client, senha="chute")

    assert _contar(pool, "sessoes") == 1
    assert _contar(pool, "tentativas_de_login") == 4

    await _entrar(client)

    assert _contar(pool, "sessoes") == 1  # só a nova
    assert _contar(pool, "tentativas_de_login") == 2


async def test_sessao_expirada_da_401(client, pool):
    token = (await _entrar(client)).json()["token"]
    with pool.connection() as conn:
        conn.execute("UPDATE sessoes SET expira_em = now() - interval '1 second'")

    for rota in ("/acesso/eu", "/clientes"):
        resp = await client.get(rota, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401, rota
        assert resp.json() == SEM_SESSAO
        assert resp.headers["WWW-Authenticate"] == "Bearer"


async def test_sair_derruba_a_sessao_e_pode_repetir(client):
    token = (await _entrar(client)).json()["token"]
    bearer = {"Authorization": f"Bearer {token}"}

    assert (await client.post("/acesso/sair", headers=bearer)).status_code == 204
    assert (await client.get("/acesso/eu", headers=bearer)).status_code == 401
    assert (await client.get("/clientes", headers=bearer)).status_code == 401
    assert (await client.post("/acesso/sair", headers=bearer)).status_code == 204
    assert (await client.post("/acesso/sair")).status_code == 204


async def test_toda_rota_protegida_sem_bearer_da_401_e_health_continua_aberta(banco, pool):
    """Percorre as rotas do contrato (o OpenAPI do app), então uma rota nova que esqueça a
    sessão quebra este teste."""
    app = _app(banco, pool)
    protegidas = [
        (metodo.upper(), caminho)
        for caminho, metodos in app.openapi()["paths"].items()
        for metodo in metodos
        if (metodo.upper(), caminho) not in ABERTAS
    ]
    assert len(protegidas) >= 20

    async with _cliente(app) as client:
        for metodo, caminho in protegidas:
            url = caminho.format_map({nome: NENHUMA for nome in _parametros(caminho)})
            for headers in ({}, {"Authorization": "Bearer inventado"}, {"Authorization": "x"}):
                resp = await client.request(metodo, url, headers={"X-Cliente-Id": "c1", **headers})
                assert resp.status_code == 401, (metodo, caminho, headers)
                assert resp.json() == SEM_SESSAO
        assert (await client.get("/health")).status_code == 200


async def test_sessao_vale_nas_rotas_protegidas(client, sessao):
    assert (await client.get("/clientes", headers=sessao)).status_code == 200
    assert (await client.get("/atendente/aprovacoes", headers=sessao)).status_code == 200
    assert (await client.get("/avaliacao/amostra", headers=sessao)).status_code == 200


async def test_sem_login_configurado_ninguem_entra_e_a_api_avisa(banco, pool, caplog):
    with caplog.at_level(logging.WARNING, logger="ampere.api.app"):
        _app(banco, pool)
        assert caplog.text == ""
        app = _app(banco, pool, login_email="", login_senha_hash="")

    assert "LOGIN_EMAIL" in caplog.text
    async with _cliente(app) as client:
        assert (await _entrar(client)).status_code == 401
        assert (await _entrar(client, email="")).status_code == 401


async def test_hash_estragado_na_configuracao_da_401(banco, pool):
    app = _app(banco, pool, login_email=EMAIL, login_senha_hash="$scrypt$estragado")

    async with _cliente(app) as client:
        resp = await _entrar(client)

    assert resp.status_code == 401
    assert resp.json() == FALHOU


# --- rajadas ----------------------------------------------------------------------------


class _ConferirEspiao:
    """Troca o scrypt por uma espera fixa e conta quantas senhas foram conferidas e quantas
    ao mesmo tempo, no pico."""

    def __init__(self, segundos: float, resultado: bool = False):
        self.segundos, self.resultado = segundos, resultado
        self.chamadas = self.ativos = self.pico = 0
        self._trava = threading.Lock()

    def __call__(self, senha: str, hash_: str) -> bool:
        with self._trava:
            self.chamadas += 1
            self.ativos += 1
            self.pico = max(self.pico, self.ativos)
        time.sleep(self.segundos)
        with self._trava:
            self.ativos -= 1
        return self.resultado


async def test_rajada_de_logins_errados_nao_trava_as_outras_rotas(banco, pool, sessao, monkeypatch):
    """Trinta logins errados ao mesmo tempo, cada um de um IP, com o scrypt lento: no máximo 4
    conferem a senha juntos, quem não consegue a vez logo recebe 503, nenhum dá 500, e a
    sessão aberta continua sendo atendida na hora, porque o login não segura conexão do pool
    nem thread enquanto espera."""
    espiao = _ConferirEspiao(segundos=0.3)
    monkeypatch.setattr(rotas_de_acesso, "conferir", espiao)

    async with _cliente(_app(banco, pool)) as client:

        async def eu_no_meio_da_rajada():
            await asyncio.sleep(0.1)
            inicio = time.monotonic()
            resp = await client.get("/acesso/eu", headers=sessao)
            return resp, time.monotonic() - inicio

        rajada = [
            _entrar(client, senha="chute", headers={"X-Ip-Do-Cliente": f"198.51.100.{i}"})
            for i in range(30)
        ]
        *logins, (eu, demora) = await asyncio.gather(*rajada, eu_no_meio_da_rajada())

    assert eu.status_code == 200
    assert demora < 1.0
    estados = [resp.status_code for resp in logins]
    assert set(estados) <= {401, 429, 503}, estados
    assert 1 <= espiao.pico <= 4
    ocupado = next(resp for resp in logins if resp.status_code == 503)
    assert ocupado.json() == {"detail": "Muitas tentativas agora. Tente de novo em instantes."}
    assert ocupado.headers["Retry-After"] == "1"


async def test_rajada_do_mesmo_ip_confere_no_maximo_cinco_senhas(client, pool, monkeypatch):
    """Cada tentativa entra no banco como falha antes do scrypt, e só então a janela é contada,
    já com ela. Assim as que correm juntas se enxergam, e uma rajada de um IP só não consegue
    conferir mais senhas que o limite."""
    espiao = _ConferirEspiao(segundos=0.1)
    monkeypatch.setattr(rotas_de_acesso, "conferir", espiao)

    respostas = await asyncio.gather(*[_entrar(client, senha="chute") for _ in range(20)])

    estados = [resp.status_code for resp in respostas]
    assert set(estados) <= {401, 429, 503}, estados
    assert 1 <= espiao.chamadas <= 5
    assert estados.count(401) == espiao.chamadas
    assert _contar(pool, "tentativas_de_login") == espiao.chamadas


class _PoolEsgotado:
    """Um pool em que nunca sobra conexão."""

    def connection(self, timeout: float | None = None):
        raise PoolTimeout("sem conexão livre")


async def test_pool_esgotado_vira_503_rapido_e_nao_prende_a_vez_do_login():
    config = Config(modelos_falsos=True, login_email=EMAIL, login_senha_hash=HASH)
    app = criar_app(config, pool=_PoolEsgotado(), verificar_qdrant=lambda: True)
    ocupado = {"detail": "Banco ocupado. Tente de novo em instantes."}

    async with _cliente(app) as client:
        for _ in range(6):  # mais que as 4 vagas: a vez é devolvida mesmo com erro
            resp = await _entrar(client)
            assert resp.status_code == 503
            assert resp.json() == ocupado
            assert resp.headers["Retry-After"] == "1"
        eu = await client.get("/acesso/eu", headers={"Authorization": "Bearer qualquer"})
        sair = await client.post("/acesso/sair", headers={"Authorization": "Bearer qualquer"})

    assert (eu.status_code, eu.json()) == (503, ocupado)
    assert (sair.status_code, sair.json()) == (503, ocupado)


def _parametros(caminho: str) -> list[str]:
    return [parte[1:-1] for parte in caminho.split("/") if parte.startswith("{")]
