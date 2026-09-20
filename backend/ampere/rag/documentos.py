"""Documentos da Base de Conhecimento: markdown com quatro metadados no frontmatter."""

from pathlib import Path

import frontmatter
from pydantic import BaseModel


class Documento(BaseModel):
    nome: str
    texto: str
    categoria: str
    produto: str
    vigencia: str
    tipo: str


def carregar_documentos(pasta: Path) -> list[Documento]:
    """Lê todo `*.md` da pasta; o nome do documento é o nome do arquivo."""
    documentos = []
    for caminho in sorted(Path(pasta).glob("*.md")):
        post = frontmatter.load(caminho)
        documentos.append(
            Documento(
                nome=caminho.name,
                texto=post.content.strip(),
                categoria=str(post["categoria"]),
                produto=str(post["produto"]),
                vigencia=str(post["vigencia"]),
                tipo=str(post["tipo"]),
            )
        )
    return documentos
