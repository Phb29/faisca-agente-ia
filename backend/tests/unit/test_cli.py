"""Os comandos dos evals gravam a execução completa no banco, a menos de `--sem-salvar` ou
de uma rodada parcial (`--amostra`); `hash-senha` imprime um hash que confere com a senha; e
`api --host ::` escuta IPv6 e IPv4 na mesma porta."""

import socket
import sys
import types

import uvicorn
from typer.testing import CliRunner

from ampere import cli
from ampere.acesso.senha import conferir
from ampere.evals.relatorio import Relatorio
from ampere.nucleo.config import Config

RELATORIO = Relatorio(contexto={"n": 1}, resumo={"n": 1}, casos=[])


async def _app_vazio(scope, receive, send) -> None:
    pass


def _capturar_salvos(monkeypatch) -> list:
    salvos: list = []
    monkeypatch.setattr(
        cli,
        "_salvar",
        lambda eval, relatorio, *, sem_salvar: salvos.append((eval, relatorio, sem_salvar)),
    )
    return salvos


def test_calibracao_grava_como_eval_juiz(monkeypatch):
    salvos = _capturar_salvos(monkeypatch)
    monkeypatch.setattr("ampere.evals.calibracao.rodar", lambda config, *, seed: RELATORIO)

    resultado = CliRunner().invoke(cli.evals, ["calibracao"])

    assert resultado.exit_code == 0, resultado.output
    assert salvos == [("juiz", RELATORIO, False)]


def test_sem_salvar_chega_ao_salvar(monkeypatch):
    salvos = _capturar_salvos(monkeypatch)
    monkeypatch.setattr("ampere.evals.calibracao.rodar", lambda config, *, seed: RELATORIO)

    resultado = CliRunner().invoke(cli.evals, ["calibracao", "--sem-salvar"])

    assert resultado.exit_code == 0, resultado.output
    assert salvos == [("juiz", RELATORIO, True)]


def test_rodada_parcial_do_rag_nao_e_gravada(monkeypatch):
    salvos = _capturar_salvos(monkeypatch)
    monkeypatch.setattr(
        "ampere.evals.rag.rodar", lambda config, *, so_retrieval, amostra: RELATORIO
    )

    resultado = CliRunner().invoke(cli.evals, ["rag", "--amostra", "5"])

    assert resultado.exit_code == 0, resultado.output
    assert salvos == []
    assert "não é gravada" in resultado.output


def test_amostra_zero_tambem_e_parcial(monkeypatch):
    salvos = _capturar_salvos(monkeypatch)
    monkeypatch.setattr(
        "ampere.evals.rag.rodar", lambda config, *, so_retrieval, amostra: RELATORIO
    )

    resultado = CliRunner().invoke(cli.evals, ["rag", "--amostra", "0"])

    assert resultado.exit_code == 0, resultado.output
    assert salvos == []


def test_rag_completo_grava_como_eval_rag(monkeypatch):
    salvos = _capturar_salvos(monkeypatch)
    monkeypatch.setattr(
        "ampere.evals.rag.rodar", lambda config, *, so_retrieval, amostra: RELATORIO
    )

    resultado = CliRunner().invoke(cli.evals, ["rag", "--so-retrieval"])

    assert resultado.exit_code == 0, resultado.output
    assert salvos == [("rag", RELATORIO, False)]


def test_salvar_sem_banco_avisa_e_segue(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "config", lambda: Config(database_url="postgresql://x:y@127.0.0.1:1/nada")
    )

    cli._salvar("juiz", RELATORIO, sem_salvar=False)

    assert "não gravada" in capsys.readouterr().out


def test_salvar_ignora_relatorio_vazio_e_sem_salvar(monkeypatch):
    monkeypatch.setattr(cli, "config", lambda: (_ for _ in ()).throw(AssertionError("tocou")))

    cli._salvar("rag", None, sem_salvar=False)
    cli._salvar("rag", RELATORIO, sem_salvar=True)


def test_hash_senha_le_a_senha_da_entrada_padrao():
    resultado = CliRunner().invoke(cli.app, ["hash-senha"], input="uma senha longa\n")

    assert resultado.exit_code == 0, resultado.output
    hash_ = resultado.output.strip()
    assert hash_.startswith("scrypt:")
    assert conferir("uma senha longa", hash_)
    assert "uma senha longa" not in resultado.output


def test_hash_senha_recusa_senha_vazia():
    resultado = CliRunner().invoke(cli.app, ["hash-senha"], input="\n")

    assert resultado.exit_code != 0
    assert "scrypt:" not in resultado.output


def _api_falsa(monkeypatch) -> None:
    """Troca a montagem do sistema por um app vazio, sem carregar modelos nem abrir o banco."""
    composicao = types.ModuleType("ampere.composicao")
    composicao.montar_api = lambda cfg: _app_vazio
    monkeypatch.setitem(sys.modules, "ampere.composicao", composicao)
    monkeypatch.setattr(cli, "config", lambda: Config())
    monkeypatch.setattr(cli, "_configurar_logs", lambda: None)


def test_api_em_dois_pontos_escuta_ipv6_e_ipv4_no_mesmo_socket(monkeypatch):
    """A rede interna do Railway é IPv6, e o healthcheck pode vir por IPv4. O asyncio abre `::`
    só para IPv6, então o comando abre o socket ele mesmo, com IPV6_V6ONLY desligado."""
    _api_falsa(monkeypatch)
    servidos = []
    monkeypatch.setattr(
        uvicorn.Server, "run", lambda self, sockets=None: servidos.append((self.config, sockets))
    )

    resultado = CliRunner().invoke(cli.app, ["api", "--host", "::", "--port", "0"])

    assert resultado.exit_code == 0, resultado.output
    [(config, [sock])] = servidos
    with sock:
        assert (config.app, config.host) == (_app_vazio, "::")
        assert sock.family == socket.AF_INET6
        assert sock.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY) == 0
        assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) != 0
        endereco, porta = sock.getsockname()[:2]
        assert endereco == "::"
        sock.listen()
        for destino in ("127.0.0.1", "::1"):
            with socket.create_connection((destino, porta), timeout=2):
                sock.accept()[0].close()


def test_api_em_outro_host_sobe_como_antes(monkeypatch):
    _api_falsa(monkeypatch)
    chamadas = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: chamadas.append((app, kwargs)))

    resultado = CliRunner().invoke(cli.app, ["api"])

    assert resultado.exit_code == 0, resultado.output
    assert chamadas == [(_app_vazio, {"host": "0.0.0.0", "port": 8000})]
