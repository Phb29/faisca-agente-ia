"""Prompts do juiz, um arquivo markdown por pergunta binária, com nome e versão no frontmatter.

Mesmo formato e mesmo carregador de `ampere.grafo.prompts`; só a pasta muda.
"""

from pathlib import Path

from ampere.grafo.prompts import Prompt
from ampere.grafo.prompts import carregar_prompt as _carregar_prompt

PASTA = Path(__file__).parent
NOMES = ("fidelidade", "relevancia", "resolucao")

__all__ = ["NOMES", "PASTA", "Prompt", "carregar_prompt"]


def carregar_prompt(nome: str) -> Prompt:
    return _carregar_prompt(nome, PASTA)
