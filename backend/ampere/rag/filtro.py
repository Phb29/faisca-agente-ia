"""FiltroDeBusca (o que o self-querying gera) e o tradutor para Filter do Qdrant."""

from datetime import UTC, date, datetime

from pydantic import BaseModel, Field
from qdrant_client import models

PRODUTO_GERAL = "todos"


class FiltroDeBusca(BaseModel):
    """Metadados opcionais extraídos da pergunta do Cliente. Campo vazio não filtra."""

    categoria: str | None = Field(
        default=None,
        description="troca, devolucao, frete, garantia, pagamento ou cadastro",
    )
    produto: str | None = Field(
        default=None, description="notebooks, celulares, acessorios ou todos"
    )
    tipo: str | None = Field(default=None, description="politica ou procedimento")
    vigencia_minima: date | None = Field(
        default=None, description="só regras que valem a partir desta data"
    )


def _igual(campo: str, valor: str) -> models.FieldCondition:
    return models.FieldCondition(key=campo, match=models.MatchValue(value=valor))


def traduzir_filtro(filtro: FiltroDeBusca | None) -> models.Filter | None:
    """Campos None são ignorados; `produto` aceita o valor ou "todos"; tudo None -> None."""
    if filtro is None:
        return None
    must: list[models.Condition] = []
    if filtro.categoria:
        must.append(_igual("categoria", filtro.categoria))
    if filtro.tipo:
        must.append(_igual("tipo", filtro.tipo))
    if filtro.produto:
        must.append(
            models.Filter(
                should=[_igual("produto", filtro.produto), _igual("produto", PRODUTO_GERAL)]
            )
        )
    if filtro.vigencia_minima:
        inicio = datetime.combine(filtro.vigencia_minima, datetime.min.time(), tzinfo=UTC)
        must.append(models.FieldCondition(key="vigencia", range=models.DatetimeRange(gte=inicio)))
    if not must:
        return None
    return models.Filter(must=must)
