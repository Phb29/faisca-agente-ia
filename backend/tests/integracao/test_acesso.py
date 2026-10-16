"""Acesso: sessões e limite de tentativas no Postgres."""

import hashlib

import pytest

from ampere.acesso.sessoes import (
    criar_sessao,
    encerrar_sessao,
    limpar_expiradas,
    sessao_valida,
)
from ampere.acesso.tentativas import bloqueio, limpar_antigas, registrar

pytestmark = pytest.mark.integracao

EMAIL = "dono@exemplo.com.br"


def _falhas(conn, quantas: int, *, email=EMAIL, ip="10.0.0.1", ha_minutos: float = 0) -> None:
    for _ in range(quantas):
        conn.execute(
            "INSERT INTO tentativas_de_login (email, ip, sucesso, momento) "
            "VALUES (%s, %s, false, now() - make_interval(secs => %s))",
            (email, ip, ha_minutos * 60),
        )


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


def test_cinco_falhas_do_mesmo_ip_bloqueiam_ate_a_mais_antiga_sair_da_janela(pool):
    with pool.connection() as conn:
        _falhas(conn, 4, ip="10.0.0.1")
        assert bloqueio(conn, EMAIL, "10.0.0.1") is None

        _falhas(conn, 1, ip="10.0.0.1", ha_minutos=10)
        segundos = bloqueio(conn, EMAIL, "10.0.0.1")

        assert segundos is not None and 290 <= segundos <= 300
        assert bloqueio(conn, "outro@x.com", "10.0.0.2") is None


def test_falhas_com_mais_de_15_minutos_e_sucessos_nao_contam(pool):
    with pool.connection() as conn:
        _falhas(conn, 10, ip="10.0.0.1", ha_minutos=16)
        for _ in range(10):
            registrar(conn, EMAIL, "10.0.0.1", True)
        _falhas(conn, 4, ip="10.0.0.1")

        assert bloqueio(conn, EMAIL, "10.0.0.1") is None


def test_vinte_falhas_do_mesmo_email_bloqueiam_de_qualquer_ip(pool):
    with pool.connection() as conn:
        for i in range(19):
            registrar(conn, EMAIL, f"10.0.1.{i}", False)
        assert bloqueio(conn, EMAIL, "10.0.2.1") is None

        registrar(conn, "  dono@exemplo.com.br ", "10.0.1.99", False)

        segundos = bloqueio(conn, " dono@exemplo.com.br", "10.0.2.1")
        assert segundos is not None and 890 <= segundos <= 900
        assert bloqueio(conn, "outro@x.com", "10.0.2.1") is None


def test_limpar_antigas_apaga_so_o_que_passou_de_um_dia(pool):
    with pool.connection() as conn:
        _falhas(conn, 3, ha_minutos=25 * 60)
        _falhas(conn, 2, ha_minutos=23 * 60)

        assert limpar_antigas(conn) == 3
        restantes = conn.execute("SELECT count(*) AS n FROM tentativas_de_login").fetchone()
        assert restantes["n"] == 2
