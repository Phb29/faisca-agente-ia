"""ExecutorDoGrafo: traduz o stream do grafo nos cinco eventos da fila, sem gastar token."""

from langgraph.types import Command

from ampere.fila.executor import ExecutorDoGrafo
from ampere.fila.fila import Job
from ampere.nucleo.falsos import JevFalso
from tests.apoio import Cenario, tool_call


def job_de_mensagem(conteudo: str, conversa_id="conv-1") -> Job:
    return Job(
        id=1,
        tipo="mensagem",
        conversa_id=conversa_id,
        message_id="m1",
        payload={"conteudo": conteudo, "cliente_id": "cli_ana"},
    )


def test_caminho_duvida_emite_tool_call_tokens_e_message_done():
    cenario = Cenario(gerador=["A garantia é de doze meses."])
    executor = ExecutorDoGrafo(cenario.grafo, observabilidade=None)

    eventos = list(executor.executar(job_de_mensagem("qual a garantia?")))

    tipos = [e.tipo for e in eventos]
    assert tipos[0] == "tool_call"
    assert eventos[0].dados["nome"] == "consultar_base_de_conhecimento"
    assert tipos.count("token") > 1
    assert "".join(e.dados["texto"] for e in eventos if e.tipo == "token") == (
        "A garantia é de doze meses."
    )
    assert tipos[-1] == "message_done"
    assert eventos[-1].dados["conteudo"] == "A garantia é de doze meses."
    assert eventos[-1].dados["desfecho"] == "Resolvida"


def test_reembolso_interrompido_emite_approval_required_e_retomada_conclui():
    cenario = Cenario(
        gerador=[tool_call("emitir_reembolso", {"pedido_id": "P2", "motivo": "x"}), "Aprovado."],
        jev=JevFalso(choices={"intencao": "transacao"}),
    )
    executor = ExecutorDoGrafo(cenario.grafo, observabilidade=None)

    eventos = list(executor.executar(job_de_mensagem("reembolso do P2")))

    tipos = [e.tipo for e in eventos]
    assert "approval_required" in tipos
    assert "message_done" not in tipos
    aprovacao = next(e for e in eventos if e.tipo == "approval_required")
    assert aprovacao.dados["pedido_id"] == "P2"
    assert aprovacao.dados["valor"] == 4899.90

    retomada = Job(
        id=2,
        tipo="retomada",
        conversa_id="conv-1",
        message_id=None,
        payload={"aprovacao_id": "a1", "aprovado": True, "motivo": None, "cliente_id": "cli_ana"},
    )
    eventos = list(executor.executar(retomada))

    assert eventos[-1].tipo == "message_done"
    assert eventos[-1].dados["conteudo"] == "Aprovado."
    assert len(cenario.pedidos.reembolsos_recentes("cli_ana")) == 1


def test_erro_no_grafo_propaga_excecao_para_o_worker():
    cenario = Cenario()
    executor = ExecutorDoGrafo(cenario.grafo, observabilidade=None)
    cenario.retriever.buscar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("qdrant fora"))

    import pytest

    with pytest.raises(RuntimeError, match="qdrant fora"):
        list(executor.executar(job_de_mensagem("garantia?")))


def test_command_resume_e_montado_a_partir_do_payload():
    assert ExecutorDoGrafo.entrada_do_job(
        Job(
            id=1,
            tipo="retomada",
            conversa_id="c",
            message_id=None,
            payload={"aprovado": False, "motivo": "fora do prazo", "cliente_id": "x"},
        )
    ) == Command(resume={"aprovado": False, "motivo": "fora do prazo"})
