"""Calibração do juiz contra rótulos humanos: few-shot, TPR, TNR, desacordos e Rogan-Gladen.

Os rótulos são divididos em treino (vira few-shot do prompt de resolução), dev (mede TPR e
TNR do juiz) e teste (a taxa crua de aprovação do juiz aqui é corrigida com o TPR e o TNR
medidos no dev). Ver `metricas.py` para a fórmula e o bootstrap.
"""

import csv
import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, field_validator

from ampere.evals.juiz import Exemplo, Veredito, julgar_resolucao
from ampere.evals.metricas import MatrizDeConfusao, bootstrap_ic, matriz_de_confusao, tnr, tpr
from ampere.nucleo.config import Config

PASTA_DADOS = Path(__file__).parent / "dados"


class Rotulo(BaseModel):
    mensagem: str
    resposta: str
    aprovada: bool
    critica: str

    @field_validator("aprovada", mode="before")
    @classmethod
    def _rotulo_textual(cls, valor: object) -> object:
        if isinstance(valor, str):
            texto = valor.strip().lower()
            if texto in {"aprovada", "aprovado", "sim", "true", "1"}:
                return True
            if texto in {"reprovada", "reprovado", "nao", "não", "false", "0"}:
                return False
            raise ValueError(f"rótulo desconhecido: {valor!r}")
        return valor

    def exemplo(self) -> Exemplo:
        return Exemplo(
            mensagem=self.mensagem,
            resposta=self.resposta,
            rotulo=self.aprovada,
            critica=self.critica,
        )


def carregar_rotulos(caminho: Path = PASTA_DADOS / "rotulos_humanos.csv") -> list[Rotulo]:
    with Path(caminho).open(encoding="utf-8", newline="") as arquivo:
        return [
            Rotulo(
                mensagem=linha["mensagem"],
                resposta=linha["resposta"],
                aprovada=linha["rotulo"],
                critica=linha["critica"],
            )
            for linha in csv.DictReader(arquivo)
        ]


@dataclass(frozen=True)
class Divisao:
    treino: list[Rotulo]
    dev: list[Rotulo]
    teste: list[Rotulo]


def dividir(
    rotulos: Sequence[Rotulo],
    *,
    seed: int = 0,
    proporcoes: tuple[float, float, float] = (0.4, 0.3, 0.3),
) -> Divisao:
    """Estratificado por rótulo e determinístico: cada estrato é embaralhado com a seed e
    fatiado nas proporções; a sobra de arredondamento vai para o teste."""
    gerador = random.Random(seed)
    partes: list[list[Rotulo]] = [[], [], []]
    for valor in (True, False):
        estrato = [r for r in rotulos if r.aprovada == valor]
        gerador.shuffle(estrato)
        n_treino = round(len(estrato) * proporcoes[0])
        n_dev = round(len(estrato) * proporcoes[1])
        partes[0].extend(estrato[:n_treino])
        partes[1].extend(estrato[n_treino : n_treino + n_dev])
        partes[2].extend(estrato[n_treino + n_dev :])
    return Divisao(treino=partes[0], dev=partes[1], teste=partes[2])


@dataclass(frozen=True)
class Desacordo:
    mensagem: str
    resposta: str
    rotulo_humano: bool
    veredito: bool
    critica_juiz: str
    critica_humana: str


@dataclass(frozen=True)
class AvaliacaoDoConjunto:
    nome: str
    matriz: MatrizDeConfusao
    tpr: float
    tnr: float
    concordancia: float
    desacordos: list[Desacordo] = field(default_factory=list)
    vereditos: list[bool] = field(default_factory=list)


@dataclass(frozen=True)
class ResultadoCalibracao:
    dev: AvaliacaoDoConjunto
    teste: AvaliacaoDoConjunto
    taxa_observada: float
    taxa_corrigida: float
    intervalo: tuple[float, float]


def avaliar_conjunto(
    juiz: BaseChatModel, nome: str, rotulos: Sequence[Rotulo], few_shot: Sequence[Exemplo]
) -> AvaliacaoDoConjunto:
    vereditos: list[Veredito] = [
        julgar_resolucao(juiz, mensagem=r.mensagem, resposta=r.resposta, few_shot=few_shot)
        for r in rotulos
    ]
    humano = [r.aprovada for r in rotulos]
    juiz_disse = [v.aprovada for v in vereditos]
    matriz = matriz_de_confusao(humano, juiz_disse)
    acertos = sum(1 for h, j in zip(humano, juiz_disse, strict=True) if h == j)
    return AvaliacaoDoConjunto(
        nome=nome,
        matriz=matriz,
        tpr=tpr(matriz),
        tnr=tnr(matriz),
        concordancia=acertos / len(rotulos) if rotulos else 0.0,
        desacordos=[
            Desacordo(
                mensagem=r.mensagem,
                resposta=r.resposta,
                rotulo_humano=r.aprovada,
                veredito=v.aprovada,
                critica_juiz=v.critica,
                critica_humana=r.critica,
            )
            for r, v in zip(rotulos, vereditos, strict=True)
            if r.aprovada != v.aprovada
        ],
        vereditos=juiz_disse,
    )


def calibrar(
    juiz: BaseChatModel, divisao: Divisao, *, n_bootstrap: int = 1000
) -> ResultadoCalibracao:
    few_shot = [r.exemplo() for r in divisao.treino]
    dev = avaliar_conjunto(juiz, "dev", divisao.dev, few_shot)
    teste = avaliar_conjunto(juiz, "teste", divisao.teste, few_shot)
    if teste.vereditos:
        taxa_observada = sum(teste.vereditos) / len(teste.vereditos)
        taxa_corrigida, intervalo = bootstrap_ic(
            teste.vereditos, tpr=dev.tpr, tnr=dev.tnr, n=n_bootstrap
        )
    else:
        taxa_observada, taxa_corrigida, intervalo = 0.0, 0.0, (0.0, 0.0)
    return ResultadoCalibracao(
        dev=dev,
        teste=teste,
        taxa_observada=taxa_observada,
        taxa_corrigida=taxa_corrigida,
        intervalo=intervalo,
    )


def rodar(config: Config, *, seed: int = 0) -> ResultadoCalibracao:
    from rich.console import Console
    from rich.table import Table

    from ampere.nucleo.modelos import FabricaDeModelos

    console = Console()
    divisao = dividir(carregar_rotulos(), seed=seed)
    console.print(
        f"[dim]treino (few-shot) {len(divisao.treino)}, dev {len(divisao.dev)}, "
        f"teste {len(divisao.teste)}"
    )
    resultado = calibrar(FabricaDeModelos(config).juiz(), divisao)

    for conjunto in (resultado.dev, resultado.teste):
        m = conjunto.matriz
        tabela = Table(title=f"Juiz vs humano ({conjunto.nome}, n={sum([m.vp, m.fn, m.vn, m.fp])})")
        tabela.add_column("")
        tabela.add_column("Juiz aprovou", justify="right")
        tabela.add_column("Juiz reprovou", justify="right")
        tabela.add_row("Humano aprovou", str(m.vp), str(m.fn))
        tabela.add_row("Humano reprovou", str(m.fp), str(m.vn))
        console.print(tabela)
        console.print(
            f"TPR {conjunto.tpr:.0%}  TNR {conjunto.tnr:.0%}  "
            f"concordância {conjunto.concordancia:.0%}"
        )
        for d in conjunto.desacordos:
            console.print(
                f"[yellow]Desacordo[/yellow] humano {_rotulo(d.rotulo_humano)} / "
                f"juiz {_rotulo(d.veredito)}\n  Mensagem: {d.mensagem}\n  Resposta: {d.resposta}\n"
                f"  Crítica humana: {d.critica_humana}\n  Crítica do juiz: {d.critica_juiz}"
            )

    baixo, alto = resultado.intervalo
    console.print(
        f"\nTaxa de aprovação do juiz no teste: {resultado.taxa_observada:.0%} (crua). "
        f"Corrigida por Rogan-Gladen com TPR/TNR do dev: {resultado.taxa_corrigida:.0%} "
        f"(IC 95% por bootstrap: {baixo:.0%} a {alto:.0%})."
    )
    return resultado


def _rotulo(aprovada: bool) -> str:
    return "Aprovada" if aprovada else "Reprovada"
