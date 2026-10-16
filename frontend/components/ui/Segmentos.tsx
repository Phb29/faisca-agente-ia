"use client";

import { useId, type KeyboardEvent, type ReactNode } from "react";
import { cx } from "@/lib/cx";

type Opcao<T extends string> = { valor: T; rotulo: ReactNode };

type Props<T extends string> = {
  opcoes: Opcao<T>[];
  valor: T;
  aoMudar: (valor: T) => void;
  rotulo: string;
  className?: string;
};

/** Controle segmentado com semântica de abas (setas do teclado trocam a aba). */
export function Segmentos<T extends string>({ opcoes, valor, aoMudar, rotulo, className }: Props<T>) {
  const base = useId();

  function aoTeclar(evento: KeyboardEvent, indice: number) {
    const passo = evento.key === "ArrowRight" ? 1 : evento.key === "ArrowLeft" ? -1 : 0;
    if (!passo) return;
    evento.preventDefault();
    const proxima = opcoes[(indice + passo + opcoes.length) % opcoes.length];
    aoMudar(proxima.valor);
    document.getElementById(`${base}-${proxima.valor}`)?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={rotulo}
      className={cx("inline-flex rounded-xl bg-canvas-2 p-[3px] ring-1 ring-line ring-inset", className)}
    >
      {opcoes.map((opcao, indice) => {
        const ativa = opcao.valor === valor;
        return (
          <button
            key={opcao.valor}
            id={`${base}-${opcao.valor}`}
            type="button"
            role="tab"
            aria-selected={ativa}
            tabIndex={ativa ? 0 : -1}
            onClick={() => aoMudar(opcao.valor)}
            onKeyDown={(evento) => aoTeclar(evento, indice)}
            className={cx(
              "inline-flex h-7 flex-1 items-center justify-center gap-1.5 rounded-[9px] px-3 text-[12.5px] font-medium whitespace-nowrap transition-all",
              ativa ? "bg-surface text-ink shadow-suave" : "text-muted hover:text-ink",
            )}
          >
            {opcao.rotulo}
          </button>
        );
      })}
    </div>
  );
}
