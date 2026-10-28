"""Tudo que um modelo de linguagem lê: um arquivo markdown por prompt, com nome e versão.

O texto usa chaves duplas (`{{variavel}}`) que `renderizar` substitui; esquecer uma variável
é erro na hora, não um `{{contexto}}` vazando para o modelo. Nome e versão vão como metadata
do trace no Langfuse, para saber qual prompt produziu cada resposta.

Esta pasta é conteúdo, não lógica: qualquer conceito pode ler dela e ela não importa de
ninguém (ver docs/adr/0005).
"""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import frontmatter

PASTA = Path(__file__).parent
NOMES = (
    "gerar_resposta",
    "agente",
    "resumir_conversa",
    "resumir_ticket",
    "extrair_memorias",
    "self_querying",
    "juiz_fidelidade",
    "juiz_relevancia",
    "juiz_resolucao",
    "jev_por_llm",
)
VARIAVEL = re.compile(r"\{\{(\w+)\}\}")


@dataclass(frozen=True)
class Prompt:
    nome: str
    versao: str
    texto: str

    @property
    def variaveis(self) -> frozenset[str]:
        return frozenset(VARIAVEL.findall(self.texto))

    def renderizar(self, **valores: str) -> str:
        """Substitui todas as variáveis; falta ou sobra de variável é erro de programação."""
        faltando = self.variaveis - valores.keys()
        sobrando = valores.keys() - self.variaveis
        if faltando or sobrando:
            raise ValueError(
                f"Prompt {self.nome}: faltando {sorted(faltando)}, sobrando {sorted(sobrando)}"
            )
        return VARIAVEL.sub(lambda m: valores[m.group(1)] or "", self.texto)

    def metadata(self) -> dict[str, str]:
        return {"prompt_nome": self.nome, "prompt_versao": self.versao}


@cache
def carregar_prompt(nome: str) -> Prompt:
    caminho = PASTA / f"{nome}.md"
    if not caminho.exists():
        raise FileNotFoundError(f"Prompt não encontrado: {caminho}")
    post = frontmatter.load(caminho)
    return Prompt(nome=str(post["nome"]), versao=str(post["versao"]), texto=post.content.strip())
