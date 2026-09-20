"""Métricas dos evals: Recall@k e MRR (retrieval), TPR e TNR (juiz vs humano) e Rogan-Gladen.

Rogan-Gladen corrige a taxa crua de aprovação do juiz pelo viés dele: se o juiz aprova
`tpr` dos bons e rejeita `tnr` dos ruins, a taxa verdadeira é
(observada + tnr - 1) / (tpr + tnr - 1). O bootstrap reamostra os vereditos do juiz para
dar um intervalo de confiança dessa correção.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass


def recall_at_k(recuperados: Sequence[str], esperado: str, *, k: int) -> float:
    return 1.0 if esperado in list(recuperados)[:k] else 0.0


def mrr(recuperados: Sequence[str], esperado: str) -> float:
    for posicao, documento in enumerate(recuperados, start=1):
        if documento == esperado:
            return 1.0 / posicao
    return 0.0


@dataclass(frozen=True)
class MatrizDeConfusao:
    vp: int  # humano aprovou, juiz aprovou
    fn: int  # humano aprovou, juiz reprovou
    vn: int  # humano reprovou, juiz reprovou
    fp: int  # humano reprovou, juiz aprovou


def matriz_de_confusao(humano: Sequence[bool], juiz: Sequence[bool]) -> MatrizDeConfusao:
    pares = list(zip(humano, juiz, strict=True))
    return MatrizDeConfusao(
        vp=sum(1 for h, j in pares if h and j),
        fn=sum(1 for h, j in pares if h and not j),
        vn=sum(1 for h, j in pares if not h and not j),
        fp=sum(1 for h, j in pares if not h and j),
    )


def tpr(matriz: MatrizDeConfusao) -> float:
    positivos = matriz.vp + matriz.fn
    return matriz.vp / positivos if positivos else 0.0


def tnr(matriz: MatrizDeConfusao) -> float:
    negativos = matriz.vn + matriz.fp
    return matriz.vn / negativos if negativos else 0.0


def rogan_gladen(p_observado: float, *, tpr: float, tnr: float) -> float:
    denominador = tpr + tnr - 1
    if denominador <= 0:
        return p_observado
    corrigido = (p_observado + tnr - 1) / denominador
    return min(1.0, max(0.0, corrigido))


def bootstrap_ic(
    rotulos_juiz: Sequence[bool],
    *,
    tpr: float,
    tnr: float,
    n: int = 1000,
    seed: int = 0,
    confianca: float = 0.95,
) -> tuple[float, tuple[float, float]]:
    rotulos = list(rotulos_juiz)
    estimativa = rogan_gladen(sum(rotulos) / len(rotulos), tpr=tpr, tnr=tnr)
    gerador = random.Random(seed)
    amostras = []
    for _ in range(n):
        reamostra = gerador.choices(rotulos, k=len(rotulos))
        amostras.append(rogan_gladen(sum(reamostra) / len(reamostra), tpr=tpr, tnr=tnr))
    amostras.sort()
    cauda = (1 - confianca) / 2
    baixo = amostras[int(cauda * n)]
    alto = amostras[min(n - 1, int((1 - cauda) * n))]
    return estimativa, (min(baixo, estimativa), max(alto, estimativa))
