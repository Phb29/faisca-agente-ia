"use client";

import type { Caso, CasoJuiz, Execucao, Matriz, ResumoAmostraJuiz, ResumoCalibracao } from "@/lib/api";
import { porcento, temErro } from "@/lib/avaliacao";
import { cx } from "@/lib/cx";
import { Numeros } from "./Numeros";
import { Voz } from "./Quadrinho";
import { Quadro } from "./Quadro";

type Props = { execucao: Execucao; aoAbrirCaso: (caso: Caso) => void };

export function AbaJuiz({ execucao, aoAbrirCaso }: Props) {
  const casos = execucao.casos ?? [];
  const resumo = execucao.resumo as ResumoCalibracao | ResumoAmostraJuiz | null;
  if (!resumo || !("tamanhos" in resumo)) {
    return <AmostraDoJuiz resumo={resumo} casos={casos} aoAbrirCaso={aoAbrirCaso} />;
  }
  const { dev } = resumo;
  const n = dev.matriz.vp + dev.matriz.fn + dev.matriz.vn + dev.matriz.fp;
  const desacordos = casos.filter((caso) => !temErro(caso) && !(caso as CasoJuiz).concorda);

  return (
    <div className="animate-surgir space-y-4 [animation-delay:60ms]">
      <Numeros
        itens={[
          { rotulo: "TPR", valor: porcento(dev.tpr), sufixo: "%", detalhe: "das boas, quantas o juiz aprovou" },
          { rotulo: "TNR", valor: porcento(dev.tnr), sufixo: "%", detalhe: "das ruins, quantas o juiz pegou" },
          {
            rotulo: "Concordância",
            valor: porcento(dev.concordancia),
            sufixo: "%",
            detalhe: `${dev.matriz.vp + dev.matriz.vn} de ${n} iguais ao humano`,
          },
        ]}
      />
      <div className="grid gap-4 xl:grid-cols-[1fr_1.2fr]">
        <MatrizDeConfusao matriz={dev.matriz} n={n} />
        <Regua resumo={resumo} />
      </div>
      <Julgamentos
        id="titulo-desacordos"
        titulo="Desacordos"
        descricao="Onde juiz e humano discordaram, lado a lado. Clique para ver a resposta inteira."
        vazio="Juiz e humano concordaram em tudo."
        casos={desacordos}
        aoAbrirCaso={aoAbrirCaso}
      />
    </div>
  );
}

function MatrizDeConfusao({ matriz, n }: { matriz: Matriz; n: number }) {
  const celula = (quantidade: number, certo: boolean, rotulo: string) => (
    <div className={cx("rounded-xl p-4", certo ? "bg-sucesso-soft text-sucesso" : "bg-perigo-soft text-perigo")}>
      <p className="font-display text-[40px] leading-none font-semibold tracking-[-0.04em] tabular-nums">
        {quantidade}
      </p>
      <p className="mt-2 text-[12px]">
        {certo ? "✓ " : "✗ "}
        {rotulo}
      </p>
    </div>
  );
  return (
    <Quadro id="titulo-matriz" titulo="Juiz contra humano" descricao={`No conjunto dev, ${n} respostas.`}>
      <div className="mt-4 grid grid-cols-[110px_1fr_1fr] gap-2 text-[12px]">
        <span />
        <span className="text-center text-muted">Juiz aprovou</span>
        <span className="text-center text-muted">Juiz reprovou</span>
        <span className="self-center text-muted">Humano aprovou</span>
        {celula(matriz.vp, true, "concordou")}
        {celula(matriz.fn, false, "boa reprovada")}
        <span className="self-center text-muted">Humano reprovou</span>
        {celula(matriz.fp, false, "ruim aprovada")}
        {celula(matriz.vn, true, "concordou")}
      </div>
    </Quadro>
  );
}

function Regua({ resumo }: { resumo: ResumoCalibracao }) {
  const [baixo, alto] = resumo.intervalo;
  const posicao = (valor: number) => `${Math.round(valor * 1000) / 10}%`;
  const crua = `${porcento(resumo.taxa_observada)}%`;
  const corrigida = `${porcento(resumo.taxa_corrigida)}%`;
  const faixa = `${porcento(baixo)}% a ${porcento(alto)}%`;
  return (
    <Quadro
      id="titulo-regua"
      titulo="Quanto o chatbot acerta, de verdade?"
      descricao="O juiz erra para os dois lados. Rogan-Gladen desconta esse erro com o TPR e o TNR medidos no dev."
    >
      <div
        role="img"
        aria-label={`Taxa crua ${crua}, corrigida ${corrigida}, intervalo de confiança de ${faixa}`}
        className="relative mx-2 mt-8 h-7"
      >
        <span className="absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 bg-line-strong" />
        <span
          className="absolute top-0 h-7 rounded-md bg-volt/45 ring-1 ring-volt-forte ring-inset"
          style={{ left: posicao(baixo), width: posicao(alto - baixo) }}
        />
        <span
          className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-surface ring-2 ring-muted"
          style={{ left: posicao(resumo.taxa_observada) }}
        />
        <span
          className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink"
          style={{ left: posicao(resumo.taxa_corrigida) }}
        />
      </div>
      <div className="mx-2 mt-1 flex justify-between font-mono text-[10px] text-muted">
        <span>0%</span>
        <span>100%</span>
      </div>
      <p className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-[13px]">
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="size-3 rounded-full bg-surface ring-2 ring-muted" /> crua {crua}
        </span>
        <span className="flex items-center gap-1.5 font-semibold">
          <span aria-hidden className="size-3 rounded-full bg-ink" /> corrigida {corrigida}
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="h-3 w-5 rounded-sm bg-volt/45 ring-1 ring-volt-forte ring-inset" /> faixa{" "}
          {faixa}
        </span>
      </p>
      <p className="mt-3 text-[12.5px] leading-relaxed text-muted">
        A faixa verde é o intervalo de confiança de 95% pelo bootstrap. Com só {resumo.tamanhos.teste} respostas no
        teste, ela é larga, e isso é parte da lição.
      </p>
    </Quadro>
  );
}

function AmostraDoJuiz({
  resumo,
  casos,
  aoAbrirCaso,
}: {
  resumo: ResumoAmostraJuiz | null;
  casos: Caso[];
  aoAbrirCaso: (caso: Caso) => void;
}) {
  return (
    <div className="animate-surgir space-y-4 [animation-delay:60ms]">
      <Numeros
        itens={[
          {
            rotulo: "Concordância",
            valor: resumo ? String(resumo.concordaram) : "—",
            sufixo: resumo ? `/${resumo.n}` : undefined,
            detalhe: "respostas em que o juiz disse o mesmo que o humano",
          },
          { rotulo: "Falharam", valor: String(resumo?.erros ?? 0), detalhe: "casos que não chegaram ao fim" },
          { rotulo: "Conjunto", valor: "teste", detalhe: "nunca um exemplo do prompt" },
        ]}
      />
      <Julgamentos
        id="titulo-julgamentos"
        titulo="Respostas julgadas"
        descricao="O humano e o juiz lado a lado, para cada resposta da amostra."
        vazio="Nenhuma resposta julgada."
        casos={casos}
        aoAbrirCaso={aoAbrirCaso}
      />
    </div>
  );
}

type PropsDosJulgamentos = {
  id: string;
  titulo: string;
  descricao: string;
  vazio: string;
  casos: Caso[];
  aoAbrirCaso: (caso: Caso) => void;
};

function Julgamentos({ id, titulo, descricao, vazio, casos, aoAbrirCaso }: PropsDosJulgamentos) {
  return (
    <Quadro id={id} titulo={titulo} descricao={descricao}>
      {casos.length === 0 ? (
        <p className="mt-6 text-[13px] text-muted">{vazio}</p>
      ) : (
        <ul className="mt-3 space-y-4">
          {casos.map((caso) => (
            <li key={caso.id}>
              <button
                type="button"
                onClick={() => aoAbrirCaso(caso)}
                className="block w-full rounded-xl text-left transition-colors hover:bg-surface-2"
              >
                {temErro(caso) ? (
                  <span className="block px-3 py-2 text-[12.5px] text-perigo">
                    {caso.id} falhou: {caso.erro}
                  </span>
                ) : (
                  <Julgamento caso={caso as CasoJuiz} />
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Quadro>
  );
}

function Julgamento({ caso }: { caso: CasoJuiz }) {
  return (
    <span className="block p-1">
      <span className="block rounded-xl bg-canvas px-3 py-2 text-[12.5px] leading-relaxed text-ink-2">
        <span className="sobretitulo mr-2">{caso.conjunto}</span>
        Mensagem: “{caso.mensagem}” · Resposta: “{caso.resposta}”
      </span>
      <span className="mt-2 grid gap-2 sm:grid-cols-2">
        <Voz quem="Humano" veredito={caso.humano} />
        <Voz quem="Juiz" veredito={caso.juiz} />
      </span>
    </span>
  );
}
