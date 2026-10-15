"""Regras do Jev: as perguntas que decidem os Guardrails, o Roteador e o Gate de Aprovação.

Cada arquivo YAML desta pasta foi escrito para ser lido por qualquer pessoa, sem saber
programar: a pergunta, quando a resposta é sim, quando é não e o que acontece quando ela
dispara. Aqui o código só carrega e valida. Um arquivo inválido falha no import, e não no meio
de uma Conversa. As perguntas são tipos do projeto (`PerguntaSimNao` e `PerguntaDeEscolha`), e
quem as traduz para o SDK da TypeSafe é só o `JevReal` (ver docs/adr/0008).

Como `prompts/`, esta pasta é conteúdo: qualquer conceito lê dela e ela não importa de
ninguém (ver docs/adr/0005).
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

PASTA = Path(__file__).parent


class PerguntaSimNao(BaseModel):
    """Pergunta de sim ou não: o Jev devolve a probabilidade de a resposta ser sim."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pergunta: str
    sim_quando: str
    nao_quando: str


class PerguntaDeEscolha(BaseModel):
    """Pergunta de escolha: o Jev escolhe uma opção e devolve a probabilidade de cada uma."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pergunta: str
    opcoes: dict[str, str]


class Regras[P: PerguntaSimNao | PerguntaDeEscolha](BaseModel):
    """Um arquivo de regras: nome e versão (vão para o trace) e as perguntas, em ordem."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    nome: str
    versao: int
    regras: dict[str, P]

    def perguntas(self) -> dict[str, P]:
        """O dicionário que o Jev recebe numa única chamada."""
        return dict(self.regras)

    def metadata(self) -> dict[str, str | int]:
        return {"regras_nome": self.nome, "regras_versao": self.versao}


def carregar_regras[R: Regras](nome: str, modelo: type[R]) -> R:
    """Lê `regras/<nome>.yaml` e valida contra `modelo` (um `Regras[...]`)."""
    caminho = PASTA / f"{nome}.yaml"
    with caminho.open(encoding="utf-8") as arquivo:
        return modelo.model_validate(yaml.safe_load(arquivo))
