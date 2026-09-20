"""Prompts do juiz, um arquivo markdown por pergunta binária, com nome e versão no frontmatter.

Mesmo padrão de `ampere.grafo.prompts`: chaves duplas `{{variavel}}` que `renderizar`
substitui. A versão vai no Langfuse junto com o veredito, para saber qual prompt julgou.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import frontmatter

PASTA = Path(__file__).parent
NOMES = ("fidelidade", "relevancia", "resolucao")


@dataclass(frozen=True)
class Prompt:
    nome: str
    versao: str
    texto: str

    def renderizar(self, **variaveis: str) -> str:
        texto = self.texto
        for chave, valor in variaveis.items():
            texto = texto.replace("{{" + chave + "}}", valor or "")
        return texto

    def metadata(self) -> dict[str, str]:
        return {"prompt_nome": self.nome, "prompt_versao": self.versao}


@lru_cache
def carregar_prompt(nome: str) -> Prompt:
    caminho = PASTA / f"{nome}.md"
    if not caminho.exists():
        raise FileNotFoundError(f"Prompt não encontrado: {caminho}")
    post = frontmatter.load(caminho)
    return Prompt(nome=str(post["nome"]), versao=str(post["versao"]), texto=post.content.strip())
