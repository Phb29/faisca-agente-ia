"""Datasets e runs no Langfuse, quando há chaves configuradas; sem chaves, tudo é no-op.

Cada golden vira um dataset (itens com id estável, então rodar de novo não duplica) e cada
variante ou execução vira um run com os scores por item. Os resultados já foram calculados
pelo eval; o `task` do run só os consulta pelo id, para não gastar modelo duas vezes.
"""

from collections.abc import Callable
from typing import Any

from ampere.nucleo.config import Config
from ampere.observabilidade.langfuse import Observabilidade

Scores = dict[str, tuple[float | bool, str | None]]  # nome -> (valor, comentário)


def cliente_langfuse(config: Config) -> Any | None:
    """Reaproveita a construção do cliente feita por `Observabilidade`; None sem chaves."""
    return Observabilidade(config).cliente


def publicar_dataset(cliente: Any, nome: str, itens: list[dict[str, Any]]) -> None:
    """`itens`: dicts com `id`, `input`, `expected_output` e `metadata` opcional."""
    cliente.create_dataset(name=nome)
    for item in itens:
        cliente.create_dataset_item(
            dataset_name=nome,
            id=item["id"],
            input=item["input"],
            expected_output=item.get("expected_output"),
            metadata=item.get("metadata"),
        )


def publicar_run(
    cliente: Any,
    nome_dataset: str,
    run: str,
    resultados: dict[str, tuple[Any, Scores]],
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    """`resultados`: id do item -> (saída observada, scores). Itens sem resultado são pulados."""
    from langfuse.experiment import Evaluation

    def task(*, item: Any, **_: Any) -> Any:
        return resultados[item.id][0] if item.id in resultados else None

    def avaliar(*, item: Any = None, output: Any = None, **_: Any) -> list[Evaluation]:
        if item is None or item.id not in resultados:
            return []
        return [
            Evaluation(name=nome, value=valor, comment=comentario)
            for nome, (valor, comentario) in resultados[item.id][1].items()
        ]

    dataset = cliente.get_dataset(nome_dataset)
    itens = [item for item in dataset.items if item.id in resultados]
    if not itens:
        return
    cliente.run_experiment(
        name=nome_dataset,
        run_name=run,
        data=itens,
        task=task,
        evaluators=[_com_item(avaliar)],
        metadata=metadata,
    )
    cliente.flush()


def _com_item(avaliador: Callable[..., Any]) -> Callable[..., Any]:
    """Os avaliadores do Langfuse recebem input/output/expected_output; guardamos o id no input."""

    def envolto(*, input: Any, output: Any, **kwargs: Any) -> Any:
        item_id = input.get("id") if isinstance(input, dict) else None
        return avaliador(item=_ItemComId(item_id), output=output, **kwargs)

    return envolto


class _ItemComId:
    def __init__(self, id: str | None) -> None:
        self.id = id
