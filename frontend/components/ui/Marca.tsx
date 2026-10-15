import { cx } from "@/lib/cx";

const TAMANHOS = { xs: "size-6", sm: "size-7", md: "size-9", lg: "size-12" };

/** O símbolo da Ampère: um quadrado noite com um raio volt. */
export function Marca({ tamanho = "md", className }: { tamanho?: keyof typeof TAMANHOS; className?: string }) {
  return (
    <span
      aria-hidden
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-[30%] bg-noite ring-1 ring-noite-line ring-inset",
        TAMANHOS[tamanho],
        className,
      )}
    >
      <svg viewBox="0 0 24 24" className="size-[58%]" fill="none">
        <path d="M13.2 2.5 5.5 13.1h5.4l-1.6 8.4 7.8-10.7h-5.5l1.6-8.3Z" fill="var(--volt)" />
      </svg>
    </span>
  );
}

/** Símbolo e nome, para cabeçalhos. */
export function Logotipo({ subtitulo, claro = false }: { subtitulo?: string; claro?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <Marca tamanho="sm" />
      <span className="flex items-baseline gap-2">
        <span className={cx("font-display text-[19px] leading-none font-semibold tracking-[-0.03em]", claro ? "text-noite-texto" : "text-ink")}>
          Ampère
        </span>
        {subtitulo && <span className="sobretitulo">{subtitulo}</span>}
      </span>
    </span>
  );
}
