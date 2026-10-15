"use client";

import { X } from "lucide-react";
import { useEffect, useState } from "react";
import type { Caso, CasoAgente, CasoJuiz, CasoRag, NomeDoEval } from "@/lib/api";
import { relogio, rotuloDaFase, rotuloDoGrupo, segundos, TAMANHO_DA_AMOSTRA, TEXTOS, temErro } from "@/lib/avaliacao";
import { cx } from "@/lib/cx";
import { terminada, type AoVivo, type Cartao } from "@/hooks/useAmostraAoVivo";
import { Quadrinho, QuadrinhosDoAgente } from "./Quadrinho";

type Props = {
  nome: NomeDoEval;
  estado: AoVivo;
  aoAbrirCaso: (caso: Caso) => void;
  aoDispensar: () => void;
};

/** A faixa escura da amostra: um cartão por caso, com as fases enquanto roda e o resultado. */
export function FaixaAoVivo({ nome, estado, aoAbrirCaso, aoDispensar }: Props) {
  const fim = terminada(estado.status);
  const prontos = estado.cartoes.filter((c) => c.estado === "pronto").length;
  const meio = estado.cartoes.some((c) => c.estado === "rodando") ? 0.5 : 0;
  // Só a conclusão de verdade enche a barra: um erro no meio do caminho mostra o quanto deu.
  const progresso = estado.status === "concluida" ? 100 : ((prontos + meio) / TAMANHO_DA_AMOSTRA) * 100;

  return (
    <section
      aria-label="Amostra ao vivo"
      className="mb-6 animate-surgir rounded-2xl bg-noite p-5 text-noite-texto shadow-elevada"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span
          aria-hidden
          className={cx("size-2 rounded-full", fim ? "bg-noite-muted" : "animate-pulso bg-volt ring-4 ring-volt/20")}
        />
        <h2 aria-live="polite" className="text-[15px] font-semibold tracking-[-0.01em]">
          {titulo(estado, nome)}
        </h2>
        <span className="font-mono text-[11px] text-noite-muted">mesma fila e mesmo stream do chat</span>
        <div className="ml-auto flex items-center gap-3 font-mono text-[11px] text-noite-muted">
          {estado.conexao === "reconectando" && (
            <span role="status" className="text-volt">
              reconectando…
            </span>
          )}
          <Tempo estado={estado} />
          {fim && (
            <button
              type="button"
              onClick={aoDispensar}
              aria-label="Fechar a faixa da amostra"
              className="rounded-md p-1 transition-colors hover:bg-noite-2 hover:text-noite-texto focus-visible:outline-volt"
            >
              <X aria-hidden className="size-4" />
            </button>
          )}
        </div>
      </div>

      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={TAMANHO_DA_AMOSTRA}
        aria-valuenow={prontos}
        aria-valuetext={`${prontos} de ${TAMANHO_DA_AMOSTRA} prontos`}
        className="mt-3 h-[3px] overflow-hidden rounded-full bg-noite-line"
      >
        <span aria-hidden className="block h-full bg-volt transition-[width] duration-500" style={{ width: `${progresso}%` }} />
      </div>

      <ol className="mt-4 grid gap-3 md:grid-cols-3">
        {estado.cartoes.length > 0
          ? estado.cartoes.map((cartao) => (
              <li key={cartao.id}>
                <CartaoDoCaso nome={nome} cartao={cartao} aoAbrir={aoAbrirCaso} />
              </li>
            ))
          : Array.from({ length: TAMANHO_DA_AMOSTRA }, (_, indice) => (
              <li key={indice} className="h-[136px] rounded-xl bg-noite-2 ring-1 ring-noite-line ring-inset" />
            ))}
      </ol>

      {estado.status === "erro" && (
        <p role="alert" className="mt-4 rounded-lg bg-perigo/25 px-3 py-2 text-[13px]">
          A amostra parou: {estado.erro}
        </p>
      )}
      {estado.status === "concluida" && <Resumo nome={nome} cartoes={estado.cartoes} />}
    </section>
  );
}

function titulo(estado: AoVivo, nome: NomeDoEval): string {
  if (estado.status === "pendente") return "Na fila, esperando um worker";
  if (estado.status === "rodando") return `Ao vivo · amostra de 3 ${TEXTOS[nome].unidade}`;
  if (estado.status === "concluida") return "Amostra concluída";
  return "A amostra parou";
}

function Tempo({ estado }: { estado: AoVivo }) {
  const [agora, setAgora] = useState(() => Date.now());
  const fim = terminada(estado.status);
  useEffect(() => {
    if (fim || !estado.iniciadaEm) return;
    const intervalo = setInterval(() => setAgora(Date.now()), 1000);
    return () => clearInterval(intervalo);
  }, [fim, estado.iniciadaEm]);

  if (fim) {
    const total = estado.cartoes.reduce((soma, c) => soma + (c.caso?.duracao_s ?? 0), 0);
    // Parou antes do 1º caso: não tem total nenhum para mostrar.
    return total > 0 ? <span>{segundos(total)} no total</span> : null;
  }
  if (!estado.iniciadaEm) return <span>na fila</span>;
  return <span>{relogio(agora - new Date(estado.iniciadaEm).getTime())}</span>;
}

function CartaoDoCaso({ nome, cartao, aoAbrir }: { nome: NomeDoEval; cartao: Cartao; aoAbrir: (caso: Caso) => void }) {
  const { caso } = cartao;
  const situacao = caso ? segundos(caso.duracao_s) : cartao.estado === "rodando" ? "rodando" : "na fila";
  const corpo = (
    <>
      <span className="flex justify-between gap-2 font-mono text-[10.5px] text-noite-muted">
        <span className="truncate">
          {cartao.id} · {rotuloDoGrupo(cartao.grupo)}
        </span>
        <span className="shrink-0">{situacao}</span>
      </span>
      <span
        className={cx(
          "mt-2 mb-3 line-clamp-3 text-[13.5px] leading-snug",
          cartao.estado === "aguardando" ? "text-noite-muted" : "text-noite-texto",
        )}
      >
        “{cartao.texto}”
      </span>
      <span className="mt-auto block">{caso ? <ResultadoNoCartao nome={nome} caso={caso} /> : <Fases cartao={cartao} />}</span>
    </>
  );
  const classes = cx(
    "flex h-full min-h-[136px] w-full flex-col rounded-xl bg-noite-2 p-3.5 text-left ring-1 ring-inset",
    cartao.estado === "rodando" ? "ring-volt-forte" : "ring-noite-line",
  );
  if (!caso) return <div className={classes}>{corpo}</div>;
  return (
    <button
      type="button"
      onClick={() => aoAbrir(caso)}
      className={cx(classes, "transition-colors hover:bg-noite-line focus-visible:outline-volt")}
    >
      {corpo}
    </button>
  );
}

function Fases({ cartao }: { cartao: Cartao }) {
  if (cartao.estado === "aguardando") {
    return <span className="font-mono text-[10.5px] text-noite-muted">aguardando</span>;
  }
  return (
    <span className="flex flex-wrap gap-1">
      {cartao.fases.map((fase, indice) => (
        <span
          key={`${fase}-${indice}`}
          className={cx(
            "rounded-md px-1.5 py-0.5 font-mono text-[10px]",
            indice === cartao.fases.length - 1 ? "bg-volt font-medium text-noite" : "bg-noite-line text-noite-texto",
          )}
        >
          {rotuloDaFase(fase)}
        </span>
      ))}
    </span>
  );
}

function ResultadoNoCartao({ nome, caso }: { nome: NomeDoEval; caso: Caso }) {
  if (temErro(caso)) {
    return <span className="line-clamp-3 text-[12px] text-noite-texto">falhou: {caso.erro}</span>;
  }
  if (nome === "agente") return <QuadrinhosDoAgente caso={caso} escuro />;
  if (nome === "rag") {
    const c = caso as CasoRag;
    return (
      <span className="flex items-center gap-1.5">
        <Quadrinho ok={c.posicao !== null} rotulo="Achou o documento" escuro />
        <span className="mr-2 font-mono text-[10.5px] text-noite-muted">
          {c.posicao ? `${c.posicao}º lugar` : "fora do top 5"}
        </span>
        <Quadrinho ok={c.fidelidade?.aprovada ?? null} rotulo="Fidelidade" escuro />
        <Quadrinho ok={c.relevancia?.aprovada ?? null} rotulo="Relevância" escuro />
      </span>
    );
  }
  const c = caso as CasoJuiz;
  return (
    <span className="flex items-center gap-1.5 font-mono text-[10.5px] text-noite-muted">
      humano <Quadrinho ok={c.humano.aprovada} rotulo="Humano" escuro tamanho="sm" verbos={["aprovou", "reprovou"]} />
      juiz <Quadrinho ok={c.juiz.aprovada} rotulo="Juiz" escuro tamanho="sm" verbos={["aprovou", "reprovou"]} />
      <span className={cx("ml-1", c.concorda ? "text-volt" : "text-noite-texto")}>
        {c.concorda ? "concordaram" : "discordaram"}
      </span>
    </span>
  );
}

function Resumo({ nome, cartoes }: { nome: NomeDoEval; cartoes: Cartao[] }) {
  const casos = cartoes.map((c) => c.caso).filter((caso): caso is Caso => caso !== null);
  const validos = casos.filter((caso) => !temErro(caso));
  const falhas = casos.length - validos.length;
  let destaque: string;
  if (nome === "agente") {
    const certos = validos.filter((c) => Object.values((c as CasoAgente).ok).every(Boolean)).length;
    destaque = `${certos} de ${casos.length} tudo certo`;
  } else if (nome === "rag") {
    const achados = validos.filter((c) => (c as CasoRag).posicao !== null).length;
    destaque = `${achados} de ${casos.length} acharam o documento`;
  } else {
    const iguais = validos.filter((c) => (c as CasoJuiz).concorda).length;
    destaque = `${iguais} de ${casos.length} iguais ao humano`;
  }
  return (
    <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-noite-line pt-4 text-[13px] text-noite-muted">
      <b className="text-[16px] font-semibold text-noite-texto">{destaque}</b>
      {falhas > 0 && <span>{falhas === 1 ? "1 falhou" : `${falhas} falharam`}</span>}
      <span className="ml-auto font-medium text-volt">clique num cartão para ver o detalhe</span>
    </div>
  );
}
