import { cx } from "@/lib/cx";

/** Anel girando, na cor do texto ao redor. */
export function Carregando({ className, rotulo = "Carregando" }: { className?: string; rotulo?: string }) {
  return (
    <span
      role="status"
      aria-label={rotulo}
      className={cx(
        "inline-block animate-giro rounded-full border-[1.5px] border-current border-r-transparent opacity-70",
        className ?? "size-4",
      )}
    />
  );
}
