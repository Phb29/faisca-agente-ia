import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import type { RotuloComTom, Tom } from "@/lib/rotulos";
import { TOM_SOLIDO, TOM_SUAVE } from "./tons";

type Props = {
  tom?: Tom;
  ponto?: boolean;
  className?: string;
  children: ReactNode;
};

export function Pilula({ tom = "neutro", ponto = false, className, children }: Props) {
  return (
    <span
      className={cx(
        "inline-flex h-[22px] shrink-0 items-center gap-1.5 rounded-full px-2 text-[11.5px] leading-none font-medium whitespace-nowrap",
        TOM_SUAVE[tom],
        className,
      )}
    >
      {ponto && <Ponto tom={tom} />}
      {children}
    </span>
  );
}

/** Pílula a partir de um rótulo de `lib/rotulos`. */
export function PilulaDe({ rotulo, className }: { rotulo: RotuloComTom; className?: string }) {
  return (
    <Pilula tom={rotulo.tom} ponto className={className}>
      {rotulo.rotulo}
    </Pilula>
  );
}

export function Ponto({ tom = "neutro", pulsando = false, className }: { tom?: Tom; pulsando?: boolean; className?: string }) {
  return (
    <span aria-hidden className={cx("relative inline-flex size-1.5 shrink-0", className)}>
      {pulsando && (
        <span className={cx("absolute inset-0 animate-ping rounded-full opacity-60", TOM_SOLIDO[tom])} />
      )}
      <span className={cx("relative size-full rounded-full", TOM_SOLIDO[tom])} />
    </span>
  );
}
