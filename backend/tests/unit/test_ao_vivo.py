"""A amostra ao vivo: sorteio, fases, cada caso gravado antes do aviso, caso que falha e
amostra liberada no meio."""

import random

import pytest

from ampere.evals import calibracao, rag
from ampere.evals.ao_vivo import LIMITE_DO_AVISO, ExecutorDeAvaliacao, evento_do_caso
from ampere.evals.execucoes import RegistroEmMemoria
from ampere.evals.juiz import Veredito
from ampere.fila.eventos import Evento
from ampere.fila.fila import Job
from ampere.nucleo.config import Config
from ampere.prompts import carregar_prompt
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


class _RegistroLiberadoAoConcluir(RegistroEmMemoria):
    """Simula a amostra liberada como abandonada entre o último caso e o `concluir`."""

    def concluir(self, execucao_id, resumo):
        self.liberar(execucao_id)
        return False


def test_amostra_liberada_apos_o_ultimo_caso_nao_emite_eval_fim():
    registro = _RegistroLiberadoAoConcluir()
    registro.criar("e1")

    eventos = list(executor(registro).executar(job("juiz")))

    assert "eval_fim" not in [e.tipo for e in eventos]
    assert registro.execucoes["e1"]["status"] == "erro"
    assert len(registro.execucoes["e1"]["casos"]) == 3


def test_contexto_tem_n_do_sorteio_prompts_versionados_e_seed_do_juiz():
    registro = registro_novo()

    list(executor(registro).executar(job("juiz")))

    contexto = registro.execucoes["e1"]["contexto"]
    assert contexto["n"] == 3
    assert contexto["prompts"] == {"juiz_resolucao": carregar_prompt("juiz_resolucao").versao}
    assert contexto["seed"] == calibracao.SEED_DA_AMOSTRA


def test_eval_fase_carrega_o_caso_id_do_caso_em_execucao():
    registro = registro_novo()

    eventos = list(executor(registro).executar(job("juiz")))

    fases = [e for e in eventos if e.tipo == "eval_fase"]
    ids_dos_casos = [c["id"] for c in registro.execucoes["e1"]["casos"]]
    assert [f.dados["caso_id"] for f in fases] == ids_dos_casos


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


def test_caso_estoura_o_limite_em_bytes_mesmo_cabendo_em_caracteres():
    caso = {"id": "rag-003", "resposta": "ã" * (LIMITE_DO_AVISO // 2 + 100)}
    texto = Evento(tipo="eval_caso", dados={"caso": caso}).model_dump_json()
    assert len(texto) < LIMITE_DO_AVISO
    assert len(texto.encode()) > LIMITE_DO_AVISO

    assert evento_do_caso(caso).dados == {"caso_id": "rag-003", "grande": True}
