"""O registro em memória segue as mesmas regras de status do Postgres, para os testes do
executor da amostra valerem para a produção."""

from ampere.evals.execucoes import TEMPO_ESGOTADO, RegistroEmMemoria, canal_da_execucao


def test_registro_em_memoria_so_grava_a_partir_do_status_certo():
    registro = RegistroEmMemoria()
    execucao_id = registro.criar()

    assert registro.anexar_caso(execucao_id, {"id": "x"}) is False
    assert registro.marcar_rodando(execucao_id, {"sorteados": []}) is True
    assert registro.marcar_rodando(execucao_id, {}) is False
    assert registro.anexar_caso(execucao_id, {"id": "a"}) is True
    registro.liberar(execucao_id)
    assert registro.anexar_caso(execucao_id, {"id": "b"}) is False
    assert registro.concluir(execucao_id, {}) is False
    assert registro.execucoes[execucao_id]["casos"] == [{"id": "a"}]
    assert registro.execucoes[execucao_id]["erro"] == TEMPO_ESGOTADO


def test_falhar_vale_para_pendente_uma_vez_so():
    registro = RegistroEmMemoria()
    execucao_id = registro.criar("e2")

    assert registro.falhar(execucao_id, "quebrou") is True
    assert registro.falhar(execucao_id, "de novo") is False
    assert registro.execucoes[execucao_id]["status"] == "erro"


def test_canal_da_execucao_e_um_identificador_valido():
    canal = canal_da_execucao("12345678-aaaa-bbbb-cccc-1234567890ab")

    assert canal == "avaliacao_12345678aaaabbbbcccc1234567890ab"
