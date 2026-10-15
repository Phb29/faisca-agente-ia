import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cx } from "@/lib/cx";
import { Carregando } from "./Carregando";

type Variante = "primario" | "secundario" | "fantasma" | "perigo";
type Tamanho = "sm" | "md" | "lg";

const VARIANTES: Record<Variante, string> = {
  primario: "bg-ink text-canvas shadow-suave hover:bg-ink-2 disabled:bg-line-strong disabled:text-muted",
  secundario:
    "bg-surface text-ink ring-1 ring-inset ring-line shadow-suave hover:bg-surface-2 hover:ring-line-strong disabled:text-muted",
  fantasma: "text-ink-2 hover:bg-canvas-2 hover:text-ink disabled:text-muted",
  perigo: "bg-perigo text-white shadow-suave hover:brightness-110 disabled:opacity-50",
};

const TAMANHOS: Record<Tamanho, string> = {
  sm: "h-8 gap-1.5 rounded-lg px-3 text-[13px]",
  md: "h-10 gap-2 rounded-xl px-4 text-sm",
  lg: "h-12 gap-2 rounded-xl px-5 text-[15px]",
};

/** As classes de um botão, para links que precisam parecer botões. */
export function estiloDeBotao(variante: Variante = "primario", tamanho: Tamanho = "md"): string {
  return cx(
    "inline-flex shrink-0 items-center justify-center font-medium whitespace-nowrap transition-[background-color,color,box-shadow,filter] duration-150 disabled:cursor-not-allowed",
    VARIANTES[variante],
    TAMANHOS[tamanho],
  );
}

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variante?: Variante;
  tamanho?: Tamanho;
  icone?: LucideIcon;
  carregando?: boolean;
  children: ReactNode;
};

export function Botao({
  variante = "primario",
  tamanho = "md",
  icone: Icone,
  carregando = false,
  disabled,
  className,
  children,
  type = "button",
  ...resto
}: Props) {
  return (
    <button
      type={type}
      disabled={disabled || carregando}
      className={cx(estiloDeBotao(variante, tamanho), className)}
      {...resto}
    >
      {carregando ? (
        <Carregando className="size-4" />
      ) : (
        Icone && <Icone aria-hidden className="size-4 shrink-0" strokeWidth={1.8} />
      )}
      {children}
    </button>
  );
}

type PropsDoIcone = ButtonHTMLAttributes<HTMLButtonElement> & {
  icone: LucideIcon;
  rotulo: string;
  tamanho?: "sm" | "md";
};

/** Botão só com ícone: o rótulo vira aria-label e title. */
export function BotaoDeIcone({ icone: Icone, rotulo, tamanho = "md", className, type = "button", ...resto }: PropsDoIcone) {
  return (
    <button
      type={type}
      aria-label={rotulo}
      title={rotulo}
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-canvas-2 hover:text-ink disabled:opacity-40",
        tamanho === "sm" ? "size-8" : "size-9",
        className,
      )}
      {...resto}
    >
      <Icone aria-hidden className="size-[18px]" strokeWidth={1.7} />
    </button>
  );
}
