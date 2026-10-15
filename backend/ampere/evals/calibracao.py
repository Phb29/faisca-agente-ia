"""Calibração do juiz contra rótulos humanos: few-shot, TPR, TNR, desacordos e Rogan-Gladen.

Os rótulos são divididos em treino (vira few-shot do prompt de resolução), dev (mede TPR e
TNR do juiz) e teste (a taxa crua de aprovação do juiz aqui é corrigida com o TPR e o TNR
medidos no dev). Ver `metricas.py` para a fórmula e o bootstrap.
"""

import csv
import random
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, field_validator

from ampere.evals.juiz import Exemplo, Veredito, julgar_resolucao
from ampere.evals.metricas import MatrizDeConfusao, bootstrap_ic, matriz_de_confusao, tnr, tpr
from ampere.evals.relatorio import PassosDoCaso, Relatorio, Sorteado, contexto_base, sem_erro
from ampere.nucleo.config import Config

PASTA_DADOS = Path(__file__).parent / "dados"
PROMPTS_DO_JUIZ = ("juiz_resolucao",)
# A seed padrão da divisão treino/dev/teste: a amostra ao vivo usa a mesma, para o few-shot
# e o sorteio do teste virem da mesma divisão.
SEED_DA_AMOSTRA = 0


class Rotulo(BaseModel):
    mensagem: str
    resposta: str
    aprovada: bool
    critica: str
    indice: int = 0  # a posição no CSV; o padrão serve aos testes que montam rótulos à mão

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
                indice=i,
                mensagem=linha["mensagem"],
                resposta=linha["resposta"],
                aprovada=linha["rotulo"],
                critica=linha["critica"],
            )
            for i, linha in enumerate(csv.DictReader(arquivo))
        ]


def id_do_rotulo(rotulo: Rotulo) -> str:
    """Id estável de uma resposta rotulada: a posição no CSV, que sobrevive ao `dividir`."""
    return f"rot-{rotulo.indice:02d}"


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
class Julgamento:
    rotulo: Rotulo
    veredito: Veredito
    duracao_s: float


def julgar_rotulo(juiz: BaseChatModel, rotulo: Rotulo, few_shot: Sequence[Exemplo]) -> Julgamento:
    inicio = time.perf_counter()
    veredito = julgar_resolucao(
        juiz, mensagem=rotulo.mensagem, resposta=rotulo.resposta, few_shot=few_shot
    )
    return Julgamento(rotulo, veredito, time.perf_counter() - inicio)


@dataclass(frozen=True)
class AvaliacaoDoConjunto:
    nome: str
    matriz: MatrizDeConfusao
    tpr: float
    tnr: float
    concordancia: float
    desacordos: list[Desacordo] = field(default_factory=list)
    vereditos: list[bool] = field(default_factory=list)
    julgamentos: list[Julgamento] = field(default_factory=list)


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
    julgamentos = [julgar_rotulo(juiz, r, few_shot) for r in rotulos]
    humano = [j.rotulo.aprovada for j in julgamentos]
    juiz_disse = [j.veredito.aprovada for j in julgamentos]
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
                mensagem=j.rotulo.mensagem,
                resposta=j.rotulo.resposta,
                rotulo_humano=j.rotulo.aprovada,
                veredito=j.veredito.aprovada,
                critica_juiz=j.veredito.critica,
                critica_humana=j.rotulo.critica,
            )
            for j in julgamentos
            if j.rotulo.aprovada != j.veredito.aprovada
        ],
        vereditos=juiz_disse,
        julgamentos=julgamentos,
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


# --- relatório e amostra ao vivo ------------------------------------------------------------


def _grupo(rotulo: Rotulo) -> str:
    return "aprovada" if rotulo.aprovada else "reprovada"


def caso_juiz(conjunto: str, julgamento: Julgamento) -> dict:
    r, v = julgamento.rotulo, julgamento.veredito
    return {
        "id": id_do_rotulo(r),
        "texto": r.mensagem,
        "grupo": _grupo(r),
        "conjunto": conjunto,
        "mensagem": r.mensagem,
        "resposta": r.resposta,
        "humano": {"aprovada": r.aprovada, "critica": r.critica},
        "juiz": v.model_dump(),
        "concorda": r.aprovada == v.aprovada,
        "duracao_s": round(julgamento.duracao_s, 2),
        "erro": None,
    }


def resumo_calibracao(divisao: Divisao, resultado: ResultadoCalibracao) -> dict:
    def conjunto(avaliacao: AvaliacaoDoConjunto) -> dict:
        return {
            "matriz": asdict(avaliacao.matriz),
            "tpr": avaliacao.tpr,
            "tnr": avaliacao.tnr,
            "concordancia": avaliacao.concordancia,
        }

    return {
        "tamanhos": {
            "treino": len(divisao.treino),
            "dev": len(divisao.dev),
            "teste": len(divisao.teste),
        },
        "dev": conjunto(resultado.dev),
        "teste": conjunto(resultado.teste),
        "taxa_observada": resultado.taxa_observada,
        "taxa_corrigida": resultado.taxa_corrigida,
        "intervalo": list(resultado.intervalo),
    }


def resumo_amostra_juiz(casos: Sequence[dict]) -> dict:
    validos = sem_erro(casos)
    return {
        "n": len(validos),
        "concordaram": sum(c["concorda"] for c in validos),
        "erros": len(casos) - len(validos),
    }


def few_shot_do_treino(
    rotulos: Sequence[Rotulo] | None = None, *, seed: int = SEED_DA_AMOSTRA
) -> list[Exemplo]:
    rotulos = list(rotulos) if rotulos is not None else carregar_rotulos()
    return [r.exemplo() for r in dividir(rotulos, seed=seed).treino]


def sortear_amostra(
    rng: random.Random, rotulos: Sequence[Rotulo] | None = None, *, seed: int = SEED_DA_AMOSTRA
) -> list[Sorteado]:
    """Três respostas só do conjunto de teste (sortear um exemplo do few-shot seria colar na
    prova), com pelo menos uma aprovada e uma reprovada pelo humano."""
    rotulos = list(rotulos) if rotulos is not None else carregar_rotulos()
    teste = dividir(rotulos, seed=seed).teste
    aprovada = rng.choice([r for r in teste if r.aprovada])
    reprovada = rng.choice([r for r in teste if not r.aprovada])
    terceira = rng.choice([r for r in teste if r is not aprovada and r is not reprovada])
    escolhidas = [aprovada, reprovada, terceira]
    rng.shuffle(escolhidas)
    return [
        Sorteado(id=id_do_rotulo(r), texto=r.mensagem, grupo=_grupo(r), item=r) for r in escolhidas
    ]


def caso_ao_vivo(
    sorteado: Sorteado, *, juiz: BaseChatModel, few_shot: Sequence[Exemplo]
) -> PassosDoCaso:
    yield "juiz"
    return caso_juiz("teste", julgar_rotulo(juiz, sorteado.item, few_shot))


def rodar(config: Config, *, seed: int = 0) -> Relatorio:
    from rich.console import Console
    from rich.table import Table

    from ampere.nucleo.modelos import FabricaDeModelos

    console = Console()
    rotulos = carregar_rotulos()
    divisao = dividir(rotulos, seed=seed)
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
    casos = [caso_juiz("dev", j) for j in resultado.dev.julgamentos] + [
        caso_juiz("teste", j) for j in resultado.teste.julgamentos
    ]
    contexto = {**contexto_base(config, prompts=PROMPTS_DO_JUIZ, n=len(rotulos)), "seed": seed}
    return Relatorio(contexto, resumo_calibracao(divisao, resultado), casos)


def _rotulo(aprovada: bool) -> str:
    return "Aprovada" if aprovada else "Reprovada"
