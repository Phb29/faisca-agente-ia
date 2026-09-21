"""Prompts dos nós do grafo, um arquivo markdown por nó, com nome e versão no frontmatter.

O texto usa chaves duplas `{{variavel}}` que `renderizar` substitui. Nome e versão vão
como metadata do trace no Langfuse, para saber qual prompt produziu cada resposta.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import frontmatter

PASTA = Path(__file__).parent
NOMES = (
    "gerar_resposta",
    "agente",
    "extrair_memorias",
    "resumir_conversa",
    "resumir_ticket",
    "self_querying",
)


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
def carregar_prompt(nome: str, pasta: Path = PASTA) -> Prompt:
    caminho = pasta / f"{nome}.md"
    if not caminho.exists():
        raise FileNotFoundError(f"Prompt não encontrado: {caminho}")
    post = frontmatter.load(caminho)
    return Prompt(nome=str(post["nome"]), versao=str(post["versao"]), texto=post.content.strip())
