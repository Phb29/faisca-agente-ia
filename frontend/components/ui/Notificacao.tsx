"use client";

import { Check, CircleAlert, X } from "lucide-react";
import { useEffect } from "react";
import { cx } from "@/lib/cx";

export type Notificacao = { id: number; tom: "sucesso" | "perigo"; texto: string };

const DURACAO_MS = 5000;

/** Aviso flutuante no canto, que some sozinho. */
export function NotificacaoFlutuante({ notificacao, aoFechar }: { notificacao: Notificacao | null; aoFechar: () => void }) {
  useEffect(() => {
    if (!notificacao) return;
    const relogio = setTimeout(aoFechar, DURACAO_MS);
    return () => clearTimeout(relogio);
  }, [notificacao, aoFechar]);

  if (!notificacao) return null;
  const Icone = notificacao.tom === "sucesso" ? Check : CircleAlert;

  return (
    <div
      key={notificacao.id}
      role={notificacao.tom === "sucesso" ? "status" : "alert"}
      className="fixed right-4 bottom-4 left-4 z-50 flex animate-surgir items-start gap-3 rounded-2xl bg-noite py-3.5 pr-3 pl-4 text-[13.5px] text-noite-texto shadow-flutuante ring-1 ring-noite-line sm:left-auto sm:max-w-[420px]"
    >
      <span
        className={cx(
          "mt-px flex size-5 shrink-0 items-center justify-center rounded-full",
          notificacao.tom === "sucesso" ? "bg-volt text-noite" : "bg-perigo text-white",
        )}
      >
        <Icone aria-hidden className="size-3" strokeWidth={2.6} />
      </span>
      <p className="min-w-0 flex-1 leading-relaxed">{notificacao.texto}</p>
      <button
        type="button"
        onClick={aoFechar}
        aria-label="Fechar aviso"
        className="-my-0.5 rounded-md p-1 text-noite-muted transition-colors hover:text-noite-texto"
      >
        <X aria-hidden className="size-4" />
      </button>
    </div>
  );
}
