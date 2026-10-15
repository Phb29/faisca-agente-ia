"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { cx } from "@/lib/cx";

type Props = {
  aberta: boolean;
  aoFechar: () => void;
  lado?: "esquerda" | "direita";
  /** Largura máxima do painel; o padrão depende do lado. */
  largura?: string;
  rotulo: string;
  className?: string;
  children: ReactNode;
};

/**
 * Painel sobreposto com fundo escurecido; fecha no Esc e no clique fora. Vai para o `body`
 * por portal, porque um ancestral animado com `transform` prenderia o `position: fixed`.
 */
export function Gaveta({ aberta, aoFechar, lado = "direita", largura, rotulo, className, children }: Props) {
  const painel = useRef<HTMLDivElement>(null);
  const aoFecharAtual = useRef(aoFechar);
  useEffect(() => {
    aoFecharAtual.current = aoFechar;
  });

  useEffect(() => {
    if (!aberta) return;
    const anterior = document.activeElement as HTMLElement | null;
    painel.current?.focus();
    const aoTeclar = (evento: KeyboardEvent) => evento.key === "Escape" && aoFecharAtual.current();
    document.addEventListener("keydown", aoTeclar);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", aoTeclar);
      document.body.style.overflow = overflow;
      anterior?.focus?.();
    };
  }, [aberta]);

  if (!aberta) return null;

  return createPortal(
    <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label={rotulo}>
      <div
        aria-hidden
        onClick={aoFechar}
        className="absolute inset-0 animate-esmaecer bg-noite/40 backdrop-blur-[2px]"
      />
      <div
        ref={painel}
        tabIndex={-1}
        className={cx(
          "absolute inset-y-0 flex w-full flex-col bg-surface shadow-flutuante outline-none",
          lado === "esquerda"
            ? "left-0 animate-gaveta-esquerda border-r border-line"
            : "right-0 animate-gaveta-direita border-l border-line",
          largura ?? (lado === "esquerda" ? "max-w-[300px]" : "max-w-xl"),
          className,
        )}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
