"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { lerDados, type DadosDoEval, type LinhaDosDados, type NomeDoEval } from "@/lib/api";
import { contagemDoGrupo, EVALS, evalValido, TEXTOS, TEXTOS_DOS_DADOS } from "@/lib/avaliacao";
import { cx } from "@/lib/cx";
import { useRecurso } from "@/hooks/useRecurso";
import { Esqueleto } from "@/components/ui/Vazio";
import { TituloDaAba } from "./CabecalhoDaAba";
import { GavetaDoDado } from "./GavetaDoDado";
import { ErroDeCarga } from "./PainelDoEval";
import { TabelaDeDados } from "./TabelaDeDados";

type Props = { aoFalhar: (erro: unknown) => void };

/** A aba Dados: o gabarito dos três evals, lido dos mesmos CSVs que o eval usa. */
export function PainelDeDados({ aoFalhar }: Props) {
  const router = useRouter();
  const escolhido = evalValido(useSearchParams().get("dataset"));
  const escolher = (nome: NomeDoEval) =>
    router.replace(`/avaliacao?aba=dados&dataset=${nome}`, { scroll: false });

  // Os três de uma vez: os cartões mostram o tamanho de cada um, e são poucas linhas.
  const recursos = {
    rag: useRecurso("dados:rag", () => lerDados("rag"), { aoErro: aoFalhar }),
    agente: useRecurso("dados:agente", () => lerDados("agente"), { aoErro: aoFalhar }),
    juiz: useRecurso("dados:juiz", () => lerDados("juiz"), { aoErro: aoFalhar }),
  };
  const atual = recursos[escolhido];
  const [linhaAberta, setLinhaAberta] = useState<LinhaDosDados | null>(null);

  return (
    <>
      <div className="flex animate-surgir flex-wrap items-end gap-x-8 gap-y-5 pt-10 pb-8">
        <TituloDaAba
          sobretitulo="Avaliação · Dados"
          pergunta="Contra o que o sistema é medido?"
          frase="O gabarito de cada eval, escrito à mão por quem conhece a Loja. É o mesmo arquivo que o eval lê, em backend/ampere/evals/dados."
        />
      </div>
      <div className="animate-surgir space-y-4 [animation-delay:60ms]">
        <div role="group" aria-label="Golden mostrado" className="grid gap-3 sm:grid-cols-3">
          {EVALS.map((nome) => (
            <Cartao
              key={nome}
              nome={nome}
              dados={recursos[nome].dados}
              ativo={nome === escolhido}
              aoEscolher={() => escolher(nome)}
            />
          ))}
        </div>
        {atual.erro && !atual.dados ? (
          <ErroDeCarga
            mensagem="Não foi possível carregar este golden."
            erro={atual.erro}
            aoRecarregar={atual.recarregar}
          />
        ) : (
          <TabelaDeDados key={escolhido} nome={escolhido} dados={atual.dados} aoAbrir={setLinhaAberta} />
        )}
      </div>
      <GavetaDoDado linha={linhaAberta} aoFechar={() => setLinhaAberta(null)} />
    </>
  );
}

type PropsDoCartao = {
  nome: NomeDoEval;
  dados: DadosDoEval | null;
  ativo: boolean;
  aoEscolher: () => void;
};

/** Um golden: o tamanho grande, para o telão, e a divisão por grupo embaixo. */
function Cartao({ nome, dados, ativo, aoEscolher }: PropsDoCartao) {
  return (
    <button
      type="button"
      aria-pressed={ativo}
      onClick={aoEscolher}
      className={cx(
        "rounded-2xl p-5 text-left shadow-suave transition-colors sm:p-6",
        ativo ? "bg-surface ring-2 ring-ink" : "bg-surface/70 ring-1 ring-line hover:bg-surface hover:ring-line-strong",
      )}
    >
      <span className="sobretitulo flex items-center justify-between gap-3">
        {TEXTOS[nome].rotulo}
        <span className="truncate tracking-normal normal-case">{TEXTOS_DOS_DADOS[nome].arquivo}</span>
      </span>
      {dados ? (
        <>
          <span className="mt-3 block font-display text-[clamp(34px,3.2vw,46px)] leading-none font-semibold tracking-[-0.04em] tabular-nums">
            {dados.n}
            <span className="ml-1.5 text-[0.36em] font-medium tracking-normal text-muted">{TEXTOS[nome].unidade}</span>
          </span>
          <span className="mt-2 block text-[13px] text-muted">
            {Object.entries(dados.grupos)
              .map(([grupo, quantidade]) => contagemDoGrupo(grupo, quantidade))
              .join(" · ")}
          </span>
        </>
      ) : (
        <span className="mt-3 block space-y-3">
          <Esqueleto className="h-10 w-20" />
          <Esqueleto className="h-3 w-40" />
        </span>
      )}
    </button>
  );
}
