"""A amostra ao vivo: sorteio, fases, cada caso gravado antes do aviso, caso que falha e
amostra liberada no meio."""

import random

import pytest

from ampere.evals import rag
from ampere.evals.ao_vivo import LIMITE_DO_AVISO, ExecutorDeAvaliacao, evento_do_caso
from ampere.evals.execucoes import RegistroEmMemoria
from ampere.evals.juiz import Veredito
from ampere.fila.fila import Job
from ampere.nucleo.config import Config
from tests.apoio import composicao_falsa

CONFIG = Config(modelos_falsos=True)


def job(eval: str) -> Job:
    return Job(
        id=1,
        tipo="eval",
        conversa_id=None,
        message_id=None,
        payload={"execucao_id": "e1", "eval": eval},
        canal="avaliacao_e1",
    )


def registro_novo() -> RegistroEmMemoria:
    registro = RegistroEmMemoria()
    registro.criar("e1")
    return registro


def executor(registro, composicao=None, sorteio=lambda: random.Random(3)) -> ExecutorDeAvaliacao:
    return ExecutorDeAvaliacao(CONFIG, composicao or composicao_falsa(), registro, sorteio=sorteio)


def test_amostra_do_juiz_conta_cada_passo_e_grava_tudo():
    registro = registro_novo()
    composicao = composicao_falsa(juiz=[Veredito(aprovada=True, critica=f"v{i}") for i in range(3)])

    eventos = list(executor(registro, composicao).executar(job("juiz")))

    assert [e.tipo for e in eventos] == [
        "eval_inicio",
        "eval_fase",
        "eval_caso",
        "eval_fase",
        "eval_caso",
        "eval_fase",
        "eval_caso",
        "eval_fim",
    ]
    sorteados = eventos[0].dados["casos"]
    assert len(sorteados) == 3
    assert [e.dados["caso"]["id"] for e in eventos if e.tipo == "eval_caso"] == [
        s["id"] for s in sorteados
    ]
    execucao = registro.execucoes["e1"]
    assert execucao["status"] == "concluida"
    assert execucao["contexto"]["sorteados"] == sorteados
    assert execucao["contexto"]["modelos_falsos"] is True
    assert len(execucao["casos"]) == 3
    assert execucao["resumo"] == eventos[-1].dados["resumo"]


def test_cada_caso_e_gravado_antes_de_o_evento_sair():
    registro = registro_novo()

    for evento in executor(registro).executar(job("juiz")):
        if evento.tipo == "eval_caso":
            gravados = [c["id"] for c in registro.execucoes["e1"]["casos"]]
            assert evento.dados["caso"]["id"] in gravados
        if evento.tipo == "eval_fim":
            assert registro.execucoes["e1"]["status"] == "concluida"


def test_amostra_da_busca_roda_na_variante_do_ar():
    registro = registro_novo()

    eventos = list(executor(registro).executar(job("rag")))

    fases = [e.dados["fase"] for e in eventos if e.tipo == "eval_fase"]
    assert fases == ["busca", "resposta", "juiz"] * 3
    execucao = registro.execucoes["e1"]
    assert execucao["contexto"]["variante"] == rag.variante_configurada(CONFIG).nome
    assert all(c["resposta"] == "Resposta padrão." for c in execucao["casos"])
    assert execucao["resumo"]["variantes"] == []


def test_amostra_do_agente_solta_os_nos_do_grafo_como_fases():
    registro = registro_novo()

    eventos = list(executor(registro).executar(job("agente")))

    fases = [e.dados["fase"] for e in eventos if e.tipo == "eval_fase"]
    assert "carregar_memoria" in fases
    assert "roteador" in fases
    assert eventos[-1].tipo == "eval_fim"
    assert {"intencao", "acao", "desfecho", "tudo"} <= set(eventos[-1].dados["resumo"])
    assert all(c["caminho"] for c in registro.execucoes["e1"]["casos"])


def test_caso_que_falha_vira_caso_com_erro_e_a_amostra_segue():
    registro = registro_novo()
    composicao = composicao_falsa()
    original = composicao.retriever.buscar
    chamadas: list[str] = []

    def buscar(pergunta, *, k=5):
        chamadas.append(pergunta)
        if len(chamadas) == 1:
            raise RuntimeError("qdrant fora")
        return original(pergunta, k=k)

    composicao.retriever.buscar = buscar

    eventos = list(executor(registro, composicao).executar(job("rag")))

    casos = registro.execucoes["e1"]["casos"]
    assert "qdrant fora" in casos[0]["erro"]
    assert set(casos[0]) == {"id", "texto", "grupo", "duracao_s", "erro"}
    assert casos[1]["erro"] is None
    assert casos[2]["erro"] is None
    assert eventos[-1].tipo == "eval_fim"
    assert eventos[-1].dados["resumo"]["n"] == 2


def test_amostra_liberada_no_meio_para_sem_dizer_mais_nada():
    registro = registro_novo()
    eventos = []

    for evento in executor(registro).executar(job("juiz")):
        eventos.append(evento)
        if evento.tipo == "eval_caso":
            registro.liberar("e1")

    tipos = [e.tipo for e in eventos]
    assert tipos.count("eval_caso") == 1
    assert "eval_fim" not in tipos
    assert len(registro.execucoes["e1"]["casos"]) == 1


def test_amostra_liberada_antes_de_comecar_nao_roda_nada():
    registro = registro_novo()
    registro.liberar("e1")

    eventos = list(executor(registro).executar(job("juiz")))

    assert [e.tipo for e in eventos] == ["error"]
    assert registro.execucoes["e1"]["casos"] == []


def test_falha_no_sorteio_marca_a_execucao_e_sobe_para_o_worker():
    registro = registro_novo()

    def quebra():
        raise RuntimeError("o csv sumiu")

    with pytest.raises(RuntimeError, match="o csv sumiu"):
        list(executor(registro, sorteio=quebra).executar(job("juiz")))

    assert registro.execucoes["e1"]["status"] == "erro"
    assert "o csv sumiu" in registro.execucoes["e1"]["erro"]


def test_eval_desconhecido_e_erro_da_execucao():
    registro = registro_novo()

    with pytest.raises(ValueError, match="nada"):
        list(executor(registro).executar(job("nada")))

    assert registro.execucoes["e1"]["status"] == "erro"


def test_caso_grande_demais_para_o_notify_vai_so_com_o_id():
    grande = {"id": "rag-001", "resposta": "x" * (LIMITE_DO_AVISO + 1)}
    pequeno = {"id": "rag-002", "resposta": "curta"}

    assert evento_do_caso(grande).dados == {"caso_id": "rag-001", "grande": True}
    assert evento_do_caso(pequeno).dados == {"caso": pequeno}
