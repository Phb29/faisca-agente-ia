import type { LucideIcon } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { cx } from "@/lib/cx";

type Props = { icone: LucideIcon; titulo: string; children?: ReactNode; className?: string };

export function Vazio({ icone: Icone, titulo, children, className }: Props) {
  return (
    <div className={cx("flex flex-col items-center px-6 py-10 text-center", className)}>
      <span className="flex size-10 items-center justify-center rounded-xl bg-surface-2 text-muted ring-1 ring-line ring-inset">
        <Icone aria-hidden className="size-[18px]" strokeWidth={1.6} />
      </span>
      <p className="mt-3 text-sm font-medium text-ink">{titulo}</p>
      {children && <div className="mt-1 max-w-xs text-[13px] leading-relaxed text-muted">{children}</div>}
    </div>
  );
}

export function Esqueleto({ className, style }: { className?: string; style?: CSSProperties }) {
  return <span aria-hidden className={cx("esqueleto block", className)} style={style} />;
}
