"use client";

import { ArrowRight, Play, RefreshCw } from "lucide-react";
import type { Execucao, NomeDoEval } from "@/lib/api";
import { descreverExecucao, fraseDaAba, TAMANHO_DA_AMOSTRA, TEXTOS } from "@/lib/avaliacao";
import { Botao } from "@/components/ui/Botao";

export type EstadoDoBotao =
  | { tipo: "livre"; depoisDeUma: boolean }
  | { tipo: "rodando"; prontos: number; disparando: boolean; naFila: boolean }
  | { tipo: "ocupado"; por: NomeDoEval };

type Props = {
  nome: NomeDoEval;
  execucoes: Execucao[] | null;
  /** A execução mostrada embaixo (a frase usa o tamanho dela). */
  mostrada: Execucao | null;
  selecionadaId: string | null;
  aoEscolher: (execucaoId: string) => void;
  botao: EstadoDoBotao;
  aoDisparar: () => void;
  aoIrPara: (nome: NomeDoEval) => void;
};

export function CabecalhoDaAba(props: Props) {
  const { nome, execucoes, mostrada, selecionadaId, aoEscolher } = props;
  const textos = TEXTOS[nome];
  const opcoes = (execucoes ?? []).filter((e) => e.status === "concluida" || e.status === "erro");

  return (
    <div className="flex animate-surgir flex-wrap items-end gap-x-8 gap-y-5 pt-10 pb-8">
      <div className="max-w-3xl min-w-0 flex-1">
        <p className="sobretitulo">{textos.sobretitulo}</p>
        <h1 className="mt-2 font-display text-[clamp(32px,3.6vw,48px)] leading-[1.04] font-semibold tracking-[-0.035em]">
          {textos.pergunta}
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-ink-2">{fraseDaAba(nome, mostrada)}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {opcoes.length > 0 && (
          <label>
            <span className="sr-only">Execução mostrada</span>
            <select
              value={selecionadaId ?? ""}
              onChange={(evento) => aoEscolher(evento.target.value)}
              className="h-10 max-w-[360px] rounded-xl bg-surface pr-8 pl-3 text-[13px] text-ink-2 shadow-suave ring-1 ring-line outline-none ring-inset focus-visible:ring-ink/40"
            >
              {selecionadaId === null && <option value="">escolha uma execução</option>}
              {opcoes.map((execucao) => (
                <option key={execucao.id} value={execucao.id}>
                  {descreverExecucao(execucao)}
                </option>
              ))}
            </select>
          </label>
        )}
        <BotaoAoVivo {...props} />
      </div>
    </div>
  );
}

function BotaoAoVivo({ nome, botao, aoDisparar, aoIrPara }: Props) {
  if (botao.tipo === "ocupado") {
    return (
      <Botao variante="secundario" icone={ArrowRight} onClick={() => aoIrPara(botao.por)}>
        Amostra do {TEXTOS[botao.por].rotulo} rodando · ver
      </Botao>
    );
  }
  if (botao.tipo === "rodando") {
    return (
      <Botao variante="volt" carregando>
        {botao.disparando
          ? "Enviando…"
          : botao.naFila
            ? "Na fila…"
            : `Rodando ${Math.min(botao.prontos + 1, TAMANHO_DA_AMOSTRA)} de ${TAMANHO_DA_AMOSTRA}`}
      </Botao>
    );
  }
  return botao.depoisDeUma ? (
    <Botao variante="secundario" icone={RefreshCw} onClick={aoDisparar}>
      Rodar outros 3
    </Botao>
  ) : (
    <Botao variante="volt" icone={Play} onClick={aoDisparar}>
      {TEXTOS[nome].botao}
    </Botao>
  );
}
