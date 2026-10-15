"""Execuções dos evals no Postgres: a completa, a amostra guardada pelo status, a liberação
das abandonadas e uma amostra por vez."""

import psycopg
import pytest

from ampere.evals.execucoes import (
    TEMPO_ESGOTADO,
    RegistroPostgres,
    amostra_em_andamento,
    anexar_caso,
    canal_da_execucao,
    concluir,
    criar_amostra,
    falhar,
    liberar_abandonadas,
    listar,
    marcar_rodando,
    obter,
    salvar_completa,
)
from ampere.fila.eventos import Evento
from ampere.nucleo.banco import conectar

pytestmark = pytest.mark.integracao


def test_salvar_completa_e_ler_de_volta(banco):
    with conectar(banco, autocommit=True) as conn:
        execucao_id = salvar_completa(
            conn,
            "agente",
            contexto={"n": 2},
            resumo={"tudo": 0.5},
            casos=[{"id": "ag01"}, {"id": "ag02"}],
        )
        lida = obter(conn, execucao_id)
        lista = listar(conn, "agente")
        de_outro_eval = listar(conn, "rag")

    assert lida["modo"] == "completa"
    assert lida["status"] == "concluida"
    assert lida["resumo"] == {"tudo": 0.5}
    assert [c["id"] for c in lida["casos"]] == ["ag01", "ag02"]
    assert [e["id"] for e in lista] == [execucao_id]
    assert "casos" not in lista[0]
    assert de_outro_eval == []


def test_amostra_anda_de_pendente_a_concluida_caso_a_caso(banco):
    with conectar(banco, autocommit=True) as conn:
        execucao_id = criar_amostra(conn, "rag")
        assert anexar_caso(conn, execucao_id, {"id": "x"}) is False, "ainda pendente"
        assert marcar_rodando(conn, execucao_id, {"sorteados": []}) is True
        assert marcar_rodando(conn, execucao_id, {}) is False, "só sai de pendente uma vez"
        assert anexar_caso(conn, execucao_id, {"id": "rag-001"}) is True
        assert anexar_caso(conn, execucao_id, {"id": "rag-002"}) is True
        assert concluir(conn, execucao_id, {"n": 2}) is True
        lida = obter(conn, execucao_id)

    assert lida["status"] == "concluida"
    assert [c["id"] for c in lida["casos"]] == ["rag-001", "rag-002"]
    assert lida["contexto"] == {"sorteados": []}
    assert lida["resumo"] == {"n": 2}
    assert lida["iniciada_em"] is not None
    assert lida["concluida_em"] is not None


def test_so_uma_amostra_por_vez_de_qualquer_eval(banco):
    with conectar(banco, autocommit=True) as conn:
        primeira = criar_amostra(conn, "rag")
        with pytest.raises(psycopg.errors.UniqueViolation):
            criar_amostra(conn, "agente")
        assert amostra_em_andamento(conn)["id"] == primeira
        falhar(conn, primeira, "quebrou")
        assert amostra_em_andamento(conn) is None
        segunda = criar_amostra(conn, "agente")

    assert segunda != primeira


def test_falhar_vale_para_pendente_e_rodando_mas_nao_depois(banco):
    with conectar(banco, autocommit=True) as conn:
        pendente = criar_amostra(conn, "juiz")
        assert falhar(conn, pendente, "o sorteio quebrou") is True
        assert obter(conn, pendente)["erro"] == "o sorteio quebrou"
        assert falhar(conn, pendente, "de novo") is False

        rodando = criar_amostra(conn, "juiz")
        marcar_rodando(conn, rodando, {})
        assert falhar(conn, rodando, "o juiz caiu") is True


def test_liberar_abandonada_avisa_a_tela_e_trava_as_escritas(banco):
    with conectar(banco, autocommit=True) as conn:
        execucao_id = criar_amostra(conn, "agente")
        marcar_rodando(conn, execucao_id, {})
        conn.execute(
            "UPDATE execucoes_de_eval SET iniciada_em = now() - interval '6 minutes' WHERE id = %s",
            (execucao_id,),
        )
        escuta = conectar(banco, autocommit=True)
        escuta.execute(f"LISTEN {canal_da_execucao(execucao_id)}")

        assert liberar_abandonadas(conn) == [execucao_id]

        avisos = [Evento.model_validate_json(n.payload) for n in escuta.notifies(timeout=1.0)]
        escuta.close()
        assert [(a.tipo, a.dados) for a in avisos] == [("error", {"mensagem": TEMPO_ESGOTADO})]
        lida = obter(conn, execucao_id)
        assert lida["status"] == "erro"
        assert lida["erro"] == TEMPO_ESGOTADO
        assert anexar_caso(conn, execucao_id, {"id": "tarde"}) is False
        assert concluir(conn, execucao_id, {}) is False
        assert obter(conn, execucao_id)["casos"] == []


def test_pendente_so_e_liberada_depois_de_dez_minutos(banco):
    with conectar(banco, autocommit=True) as conn:
        execucao_id = criar_amostra(conn, "rag")
        conn.execute(
            "UPDATE execucoes_de_eval SET criada_em = now() - interval '6 minutes' WHERE id = %s",
            (execucao_id,),
        )
        assert liberar_abandonadas(conn) == []
        conn.execute(
            "UPDATE execucoes_de_eval SET criada_em = now() - interval '11 minutes' WHERE id = %s",
            (execucao_id,),
        )
        assert liberar_abandonadas(conn) == [execucao_id]


def test_completa_nunca_e_liberada(banco):
    with conectar(banco, autocommit=True) as conn:
        salvar_completa(conn, "rag", contexto={}, resumo={}, casos=[])
        conn.execute("UPDATE execucoes_de_eval SET criada_em = now() - interval '1 day'")
        assert liberar_abandonadas(conn) == []


def test_registro_postgres_grava_pelo_pool(banco, pool):
    with conectar(banco, autocommit=True) as conn:
        execucao_id = criar_amostra(conn, "agente")
    registro = RegistroPostgres(pool)

    assert registro.marcar_rodando(execucao_id, {"sorteados": []}) is True
    assert registro.anexar_caso(execucao_id, {"id": "ag06"}) is True
    assert registro.concluir(execucao_id, {"n": 1}) is True
    assert registro.falhar(execucao_id, "tarde demais") is False

    with conectar(banco, autocommit=True) as conn:
        lida = obter(conn, execucao_id)
    assert lida["status"] == "concluida"
    assert lida["casos"] == [{"id": "ag06"}]
