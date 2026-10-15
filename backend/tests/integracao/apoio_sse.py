"""Apoio dos testes de SSE: um uvicorn de verdade numa thread (o `ASGITransport` do httpx
só devolve a resposta quando o app termina, o que nunca acontece num stream aberto) e a
leitura dos eventos de uma resposta em stream."""

import json
import socket
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager

import httpx
import uvicorn


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def servidor_no_ar(app) -> Iterator[str]:
    porta = _porta_livre()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        threading.Event().wait(0.05)
    assert server.started, "uvicorn não subiu"
    try:
        yield f"http://127.0.0.1:{porta}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


async def eventos_sse(resposta: httpx.Response) -> AsyncIterator[tuple[str, dict]]:
    """Um gerador por resposta: o httpx não deixa ler o mesmo stream duas vezes."""
    tipo, dados = None, []
    async for linha in resposta.aiter_lines():
        if linha.startswith(":"):
            continue
        if linha.startswith("event:"):
            tipo = linha[6:].strip()
        elif linha.startswith("data:"):
            dados.append(linha[5:].strip())
        elif linha == "" and tipo:
            yield tipo, json.loads("\n".join(dados))
            tipo, dados = None, []


async def coletar(resposta: httpx.Response, quantos: int) -> list[tuple[str, dict]]:
    recebidos = []
    async for tipo, dados in eventos_sse(resposta):
        recebidos.append((tipo, dados))
        if len(recebidos) == quantos:
            break
    return recebidos


async def coletar_ate(resposta: httpx.Response, finais: set[str]) -> list[tuple[str, dict]]:
    """Lê até um evento de um dos tipos `finais` ou até o servidor fechar o stream."""
    recebidos = []
    async for tipo, dados in eventos_sse(resposta):
        recebidos.append((tipo, dados))
        if tipo in finais:
            break
    return recebidos
