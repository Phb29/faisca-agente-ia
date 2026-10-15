"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";
import type { Caso, CasoRag, Execucao, ResumoRag, VarianteRag } from "@/lib/api";
import { decimal, fraseDoMrr, porcento, temErro } from "@/lib/avaliacao";
import { cx } from "@/lib/cx";
import { Pilula } from "@/components/ui/Pilula";
import { Numeros } from "./Numeros";
import { Quadro } from "./Quadro";

const VARIANTES_VISIVEIS = 6;
const SEM_GERACAO = "a geração não rodou nesta execução";

type Props = { execucao: Execucao; aoAbrirCaso: (caso: Caso) => void };

export function AbaBusca({ execucao, aoAbrirCaso }: Props) {
  const resumo = execucao.resumo as ResumoRag | null;
  const casos = execucao.casos ?? [];
  const validos = casos.filter((caso) => !temErro(caso)) as CasoRag[];
  const achadas = validos.filter((caso) => caso.posicao !== null).length;
  const semGeracao = resumo?.fidelidade == null;

  return (
    <div className="animate-surgir space-y-4 [animation-delay:60ms]">
      <Numeros
        itens={[
          {
            rotulo: "Recall@5 · no ar",
            valor: decimal(resumo?.recall_at_5),
            detalhe: `achou em ${achadas} de ${validos.length} perguntas`,
          },
          { rotulo: "MRR · no ar", valor: decimal(resumo?.mrr), detalhe: fraseDoMrr(resumo?.mrr) },
          {
            rotulo: "Fidelidade",
            valor: porcento(resumo?.fidelidade),
            sufixo: semGeracao ? undefined : "%",
            detalhe: semGeracao ? SEM_GERACAO : "a resposta se apoia nos trechos",
          },
          {
            rotulo: "Relevância",
            valor: porcento(resumo?.relevancia),
            sufixo: semGeracao ? undefined : "%",
            detalhe: semGeracao ? SEM_GERACAO : "responde o que foi perguntado",
          },
        ]}
      />
      <div className="grid gap-4 xl:grid-cols-[1.25fr_1fr]">
        <Variantes resumo={resumo} />
        <Perguntas casos={casos} aoAbrirCaso={aoAbrirCaso} />
      </div>
    </div>
  );
}

function Variantes({ resumo }: { resumo: ResumoRag | null }) {
  const [todas, setTodas] = useState(false);
  const variantes = [...(resumo?.variantes ?? [])].sort(
    (a, b) => b.recall_at_5 - a.recall_at_5 || b.mrr - a.mrr,
  );
  const visiveis = todas ? variantes : variantes.slice(0, VARIANTES_VISIVEIS);

  return (
    <Quadro
      id="titulo-variantes"
      titulo="Variantes comparadas"
      descricao="Embedder, chunker, reranker e self-querying, ordenadas por Recall@5. A destacada é a que está no ar."
    >
      {variantes.length === 0 ? (
        <p className="mt-6 text-[13px] leading-relaxed text-muted">
          Uma amostra ao vivo roda só a variante no ar ({resumo?.variante_no_ar ?? "—"}). A comparação entre
          variantes vem da execução completa.
        </p>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-[minmax(0,230px)_1fr_48px_48px] gap-x-3 border-b border-line pb-2 font-mono text-[10px] tracking-[0.08em] text-muted uppercase">
            <span>Variante</span>
            <span>Recall@5</span>
            <span className="text-right">R@5</span>
            <span className="text-right">MRR</span>
          </div>
          <ul className="mt-1">
            {visiveis.map((variante) => (
              <LinhaDaVariante
                key={variante.nome}
                variante={variante}
                noAr={variante.nome === resumo?.variante_no_ar}
              />
            ))}
          </ul>
          {variantes.length > VARIANTES_VISIVEIS && (
            <button
              type="button"
              onClick={() => setTodas(!todas)}
              className="mt-3 inline-flex items-center gap-1 text-[12.5px] text-muted transition-colors hover:text-ink"
            >
              {todas ? "mostrar menos" : `+ ${variantes.length - VARIANTES_VISIVEIS} variantes`}
              <ChevronDown aria-hidden className={cx("size-3.5 transition-transform", todas && "rotate-180")} />
            </button>
          )}
        </>
      )}
    </Quadro>
  );
}

function LinhaDaVariante({ variante, noAr }: { variante: VarianteRag; noAr: boolean }) {
  const pedacos = [
    variante.embedder,
    variante.chunker,
    variante.reranker,
    variante.self_querying ? "sq" : "sem sq",
  ];
  return (
    <li
      className={cx(
        "grid grid-cols-[minmax(0,230px)_1fr_48px_48px] items-center gap-x-3 rounded-lg py-1.5 text-[12.5px]",
        noAr && "-mx-2 bg-volt/15 px-2",
      )}
    >
      <span className="flex min-w-0 gap-1 overflow-hidden">
        {pedacos.map((pedaco, indice) => (
          <span
            key={indice}
            className="rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[10.5px] whitespace-nowrap text-ink-2 ring-1 ring-line ring-inset"
          >
            {pedaco}
          </span>
        ))}
        {noAr && <span className="sr-only">(no ar)</span>}
      </span>
      <span aria-hidden className="h-2.5 overflow-hidden rounded bg-canvas-2">
        <span
          className={cx("block h-full rounded", noAr ? "bg-volt ring-1 ring-volt-forte ring-inset" : "bg-ink")}
          style={{ width: `${Math.round(variante.recall_at_5 * 100)}%` }}
        />
      </span>
      <span className="text-right font-semibold tabular-nums">{decimal(variante.recall_at_5)}</span>
      <span className="text-right text-muted tabular-nums">{decimal(variante.mrr)}</span>
    </li>
  );
}

/** As piores primeiro: falhas, depois quem ficou fora do top 5, depois da 5ª posição à 1ª. */
function peso(caso: Caso): number {
  if (temErro(caso)) return 7;
  const { posicao } = caso as CasoRag;
  return posicao === null ? 6 : posicao;
}

function Perguntas({ casos, aoAbrirCaso }: { casos: Caso[]; aoAbrirCaso: (caso: Caso) => void }) {
  const ordenados = [...casos].sort((a, b) => peso(b) - peso(a));
  return (
    <Quadro
      id="titulo-perguntas"
      titulo="Perguntas"
      descricao="Onde o documento certo apareceu, na variante no ar. As piores primeiro; clique para ver o detalhe."
    >
      <ul className="mt-3 max-h-[480px] divide-y divide-line overflow-y-auto pr-1">
        {ordenados.map((caso) => (
          <li key={caso.id}>
            <button
              type="button"
              onClick={() => aoAbrirCaso(caso)}
              className="flex w-full items-center gap-3 rounded-md px-1 py-2.5 text-left text-[13px] transition-colors hover:bg-surface-2"
            >
              {caso.grupo === "adversarial" && (
                <Pilula tom="info" className="font-mono text-[9.5px] tracking-[0.06em] uppercase">
                  adversarial
                </Pilula>
              )}
              <span className="min-w-0 flex-1 truncate text-ink-2">{caso.texto}</span>
              <Posicao caso={caso} />
            </button>
          </li>
        ))}
      </ul>
    </Quadro>
  );
}

function Posicao({ caso }: { caso: Caso }) {
  if (temErro(caso)) return <Pilula tom="perigo">falhou</Pilula>;
  const { posicao } = caso as CasoRag;
  if (posicao === null) return <Pilula tom="perigo">fora do top 5</Pilula>;
  return <Pilula tom={posicao <= 2 ? "sucesso" : "alerta"}>{posicao}º lugar</Pilula>;
}
