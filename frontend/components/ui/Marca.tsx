import { cx } from "@/lib/cx";

const TAMANHOS = { xs: "size-6", sm: "size-7", md: "size-9", lg: "size-12" };

/** O símbolo da Faísca: um quadrado com o gradiente da marca e uma faísca de quatro pontas. */
export function Marca({ tamanho = "md", className }: { tamanho?: keyof typeof TAMANHOS; className?: string }) {
  return (
    <span
      aria-hidden
      className={cx(
        "gradiente-faisca inline-flex shrink-0 items-center justify-center rounded-[30%] shadow-[0_6px_18px_-6px_rgb(59_130_246/0.6)] ring-1 ring-white/25 ring-inset",
        TAMANHOS[tamanho],
        className,
      )}
    >
      <svg viewBox="0 0 24 24" className="size-[62%]" fill="none">
        <path d="M12 2.5c.6 4.6 2.9 6.9 7.5 9.5-4.6 2.6-6.9 4.9-7.5 9.5-.6-4.6-2.9-6.9-7.5-9.5 4.6-2.6 6.9-4.9 7.5-9.5Z" fill="#fff" />
        <circle cx="19" cy="5" r="1.4" fill="#fff" opacity="0.85" />
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
        <span className={cx("font-display text-[19px] leading-none font-bold tracking-[-0.03em]", claro ? "text-noite-texto" : "text-ink")}>
          Faísca
        </span>
        {subtitulo && <span className="sobretitulo">{subtitulo}</span>}
      </span>
    </span>
  );
}
