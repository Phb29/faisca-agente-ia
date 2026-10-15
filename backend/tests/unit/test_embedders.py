"""O MiniLM é carregado uma vez por processo, mesmo com vários `EmbedderMiniLM`."""

import sys
import types

from ampere.rag.embedders import EmbedderMiniLM, _modelo_minilm


class _VetorFalso(list):
    def tolist(self) -> list:
        return list(self)


def _fastembed_falso(chamadas: list[str]):
    modulo = types.ModuleType("fastembed")

    class TextEmbedding:
        def __init__(self, modelo: str) -> None:
            chamadas.append(modelo)

        def embed(self, textos: list[str]) -> list[_VetorFalso]:
            return [_VetorFalso([0.0]) for _ in textos]

    modulo.TextEmbedding = TextEmbedding
    return modulo


def test_minilm_e_carregado_uma_so_vez_por_processo(monkeypatch):
    chamadas: list[str] = []
    monkeypatch.setitem(sys.modules, "fastembed", _fastembed_falso(chamadas))
    _modelo_minilm.cache_clear()
    try:
        um = EmbedderMiniLM()
        dois = EmbedderMiniLM()

        um.embed(["oi"])
        dois.embed(["tchau"])

        assert len(chamadas) == 1
    finally:
        _modelo_minilm.cache_clear()
