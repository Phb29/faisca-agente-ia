"""A regra de acoplamento da ADR 0005, verificada lendo os imports de cada arquivo:

- o grafo importa das outras pastas, e nenhuma outra importa do grafo (só a raiz de
  composição, que é quem entrega o grafo à fila, à API e aos evals); a fila também não
  importa os evals, que chegam a ela como mais um executor;
- `prompts/` e `regras/` são conteúdo: qualquer um lê delas, e elas não importam de ninguém;
- o SDK de cada fornecedor só aparece no adaptador dele (ver docs/adr/0008).
"""

import ast
from pathlib import Path

import pytest

PACOTE = Path(__file__).parents[2] / "ampere"
RAIZES_DE_COMPOSICAO = {"ampere.composicao", "ampere.cli"}
ADAPTADORES_POR_SDK = {
    "typesafe_sdk": {"ampere.nucleo.jev"},
    "langchain_openai": {"ampere.nucleo.modelos", "ampere.rag.embedders"},
    "langchain_groq": {"ampere.nucleo.modelos"},
}


def _modulo(caminho: Path) -> str:
    partes = caminho.relative_to(PACOTE.parent).with_suffix("").parts
    return ".".join(partes[:-1] if partes[-1] == "__init__" else partes)


def _todos_os_imports(caminho: Path) -> set[str]:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.update(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            nomes.add(no.module)
    return nomes


TODOS_OS_IMPORTS = {
    _modulo(caminho): _todos_os_imports(caminho) for caminho in PACOTE.rglob("*.py")
}
MODULOS = {
    modulo: {nome for nome in nomes if nome.startswith("ampere")}
    for modulo, nomes in TODOS_OS_IMPORTS.items()
}


def _importa(modulo: str, alvo: str) -> bool:
    return any(nome == alvo or nome.startswith(alvo + ".") for nome in MODULOS[modulo])


@pytest.mark.parametrize("modulo", sorted(MODULOS))
def test_so_o_grafo_e_a_raiz_de_composicao_importam_do_grafo(modulo):
    if modulo.startswith("ampere.grafo") or modulo in RAIZES_DE_COMPOSICAO:
        return
    assert not _importa(modulo, "ampere.grafo"), f"{modulo} importa de ampere.grafo"


@pytest.mark.parametrize("pasta", ["ampere.prompts", "ampere.regras"])
def test_pastas_de_conteudo_nao_importam_de_ninguem(pasta):
    for modulo, imports in MODULOS.items():
        if modulo.startswith(pasta):
            assert imports <= {pasta}, f"{modulo} importa {imports - {pasta}}"


def test_a_fila_nao_sabe_que_o_grafo_existe():
    da_fila = [m for m in MODULOS if m.startswith("ampere.fila")]
    assert da_fila
    assert not any(_importa(m, "ampere.grafo") for m in da_fila)


def test_a_fila_nao_sabe_que_os_evals_existem():
    da_fila = [m for m in MODULOS if m.startswith("ampere.fila")]
    assert not any(_importa(m, "ampere.evals") for m in da_fila)


@pytest.mark.parametrize("sdk", sorted(ADAPTADORES_POR_SDK))
def test_o_sdk_de_cada_fornecedor_so_aparece_no_adaptador_dele(sdk):
    quem_importa = {
        modulo
        for modulo, nomes in TODOS_OS_IMPORTS.items()
        if any(nome == sdk or nome.startswith(sdk + ".") for nome in nomes)
    }
    assert quem_importa == ADAPTADORES_POR_SDK[sdk]
