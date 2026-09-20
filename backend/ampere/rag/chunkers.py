"""Três estratégias de chunking trocáveis por configuração.

Todas produzem `Chunk`s que cobrem o texto inteiro do documento, sem chunk vazio,
com índices sequenciais e os metadados copiados do documento.
"""

import re
from collections.abc import Callable
from typing import Protocol

import numpy as np
from pydantic import BaseModel
from sklearn.cluster import DBSCAN

from ampere.rag.documentos import Documento

Embed = Callable[[list[str]], list[list[float]]]


class Chunk(BaseModel):
    texto: str
    documento: str
    categoria: str
    produto: str
    vigencia: str
    tipo: str
    indice: int
    score: float | None = None


class Chunker(Protocol):
    nome: str

    def dividir(self, documento: Documento) -> list[Chunk]: ...


def _montar_chunks(documento: Documento, textos: list[str]) -> list[Chunk]:
    limpos = [t.strip() for t in textos if t.strip()]
    return [
        Chunk(
            texto=texto,
            documento=documento.nome,
            categoria=documento.categoria,
            produto=documento.produto,
            vigencia=documento.vigencia,
            tipo=documento.tipo,
            indice=indice,
        )
        for indice, texto in enumerate(limpos)
    ]


class ChunkerRecursivo:
    """Divide pelo separador mais grosso que aparece e desce para os mais finos
    até cada pedaço caber em `tamanho`; junta pedaços vizinhos com `sobreposicao`."""

    nome = "recursivo"
    separadores = ("\n\n", "\n", ". ", " ")

    def __init__(self, tamanho: int = 800, sobreposicao: int = 100) -> None:
        if sobreposicao >= tamanho:
            raise ValueError("sobreposicao precisa ser menor que tamanho")
        self.tamanho = tamanho
        self.sobreposicao = sobreposicao

    def dividir(self, documento: Documento) -> list[Chunk]:
        return _montar_chunks(documento, self._dividir(documento.texto, list(self.separadores)))

    def _dividir(self, texto: str, separadores: list[str]) -> list[str]:
        if len(texto) <= self.tamanho:
            return [texto]
        pecas = self._quebrar(texto, separadores)
        return self._juntar(pecas)

    def _quebrar(self, texto: str, separadores: list[str]) -> list[str]:
        """Pedaços que preservam o separador e nunca ultrapassam `tamanho`."""
        for posicao, separador in enumerate(separadores):
            if separador in texto:
                partes = texto.split(separador)
                pecas = [p + separador for p in partes[:-1]] + [partes[-1]]
                restantes = separadores[posicao + 1 :]
                resultado: list[str] = []
                for peca in pecas:
                    if len(peca) <= self.tamanho:
                        resultado.append(peca)
                    else:
                        resultado.extend(self._quebrar(peca, restantes))
                return [p for p in resultado if p]
        return [texto[i : i + self.tamanho] for i in range(0, len(texto), self.tamanho)]

    def _juntar(self, pecas: list[str]) -> list[str]:
        chunks: list[str] = []
        atual: list[str] = []
        for peca in pecas:
            if atual and len("".join(atual)) + len(peca) > self.tamanho:
                chunks.append("".join(atual))
                atual = self._cauda(atual)
                if len("".join(atual)) + len(peca) > self.tamanho:
                    atual = []
            atual.append(peca)
        if atual:
            chunks.append("".join(atual))
        return chunks

    def _cauda(self, pecas: list[str]) -> list[str]:
        """Últimas peças que cabem em `sobreposicao`, para o próximo chunk começar com elas."""
        cauda: list[str] = []
        total = 0
        for peca in reversed(pecas):
            if total + len(peca) > self.sobreposicao:
                break
            cauda.insert(0, peca)
            total += len(peca)
        return cauda


class ChunkerMarkdown:
    """Um chunk por seção de cabeçalho (#, ##, ###), com o cabeçalho no texto."""

    nome = "markdown"
    cabecalho = re.compile(r"^#{1,3}\s+\S")

    def dividir(self, documento: Documento) -> list[Chunk]:
        secoes: list[list[str]] = [[]]
        for linha in documento.texto.splitlines():
            if self.cabecalho.match(linha):
                secoes.append([])
            secoes[-1].append(linha)
        return _montar_chunks(documento, ["\n".join(s) for s in secoes])


class ChunkerSemantico:
    """Agrupa frases parecidas com DBSCAN (distância de cosseno) sobre embeddings.

    Frases do mesmo cluster viram um chunk, na ordem de primeira aparição do cluster;
    frases marcadas como ruído (-1) viram chunk próprio.
    """

    nome = "semantico"
    fronteira = re.compile(r"(?<=[.!?])\s+|\n\s*\n")

    def __init__(self, embed: Embed, eps: float = 0.5, min_samples: int = 1) -> None:
        self.embed = embed
        self.eps = eps
        self.min_samples = min_samples

    def dividir(self, documento: Documento) -> list[Chunk]:
        frases = [f.strip() for f in self.fronteira.split(documento.texto) if f.strip()]
        if not frases:
            return []
        rotulos = self._agrupar(frases)
        grupos: dict[int, list[str]] = {}
        proximo_ruido = -1
        for frase, rotulo in zip(frases, rotulos, strict=True):
            if rotulo == -1:
                rotulo = proximo_ruido
                proximo_ruido -= 1
            grupos.setdefault(rotulo, []).append(frase)
        return _montar_chunks(documento, [" ".join(g) for g in grupos.values()])

    def _agrupar(self, frases: list[str]) -> list[int]:
        if len(frases) == 1:
            return [0]
        vetores = np.array(self.embed(frases), dtype=float)
        modelo = DBSCAN(eps=self.eps, min_samples=self.min_samples, metric="cosine")
        return [int(r) for r in modelo.fit_predict(vetores)]


def criar_chunker(nome: str, embed: Embed | None = None) -> Chunker:
    if nome == "recursivo":
        return ChunkerRecursivo()
    if nome == "markdown":
        return ChunkerMarkdown()
    if nome == "semantico":
        if embed is None:
            raise ValueError("o chunker semântico precisa de uma função de embedding")
        return ChunkerSemantico(embed=embed)
    raise ValueError(f"Chunker desconhecido: {nome}")
