import type { Tom } from "@/lib/rotulos";

/** Fundo suave com texto na cor do sinal, para pílulas e selos. */
export const TOM_SUAVE: Record<Tom, string> = {
  neutro: "bg-surface-2 text-ink-2 ring-1 ring-inset ring-line",
  sucesso: "bg-sucesso-soft text-sucesso",
  alerta: "bg-alerta-soft text-alerta",
  perigo: "bg-perigo-soft text-perigo",
  info: "bg-info-soft text-info",
  volt: "bg-volt text-noite",
};

/** Cor sólida do sinal, para pontos e barras. */
export const TOM_SOLIDO: Record<Tom, string> = {
  neutro: "bg-muted",
  sucesso: "bg-sucesso",
  alerta: "bg-alerta",
  perigo: "bg-perigo",
  info: "bg-info",
  volt: "bg-volt ring-1 ring-volt-forte",
};

export const TOM_TEXTO: Record<Tom, string> = {
  neutro: "text-ink-2",
  sucesso: "text-sucesso",
  alerta: "text-alerta",
  perigo: "text-perigo",
  info: "text-info",
  volt: "text-volt-forte",
};
