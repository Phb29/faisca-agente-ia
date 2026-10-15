import { cx } from "@/lib/cx";
import { iniciais } from "@/lib/formatos";

const FUNDOS = [
  "bg-info-soft text-info",
  "bg-sucesso-soft text-sucesso",
  "bg-alerta-soft text-alerta",
  "bg-perigo-soft text-perigo",
  "bg-canvas-2 text-ink-2",
];

/** Mesma pessoa, mesma cor: o índice vem de um hash simples do id. */
function fundoDe(semente: string): string {
  let hash = 0;
  for (const letra of semente) hash = (hash * 31 + letra.charCodeAt(0)) >>> 0;
  return FUNDOS[hash % FUNDOS.length];
}

type Props = { nome: string; semente?: string; tamanho?: "sm" | "md" | "lg"; className?: string };

const TAMANHOS = { sm: "size-7 text-[10.5px]", md: "size-9 text-xs", lg: "size-11 text-sm" };

export function Avatar({ nome, semente, tamanho = "md", className }: Props) {
  return (
    <span
      aria-hidden
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold tracking-wide",
        TAMANHOS[tamanho],
        fundoDe(semente ?? nome),
        className,
      )}
    >
      {iniciais(nome)}
    </span>
  );
}
