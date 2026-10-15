import { CircleAlert, X } from "lucide-react";
import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

type Props = {
  children: ReactNode;
  aoDispensar?: () => void;
  acao?: ReactNode;
  className?: string;
};

/** Faixa de erro discreta e dispensável. */
export function Aviso({ children, aoDispensar, acao, className }: Props) {
  return (
    <div
      role="alert"
      className={cx(
        "flex animate-surgir items-start gap-3 rounded-xl bg-perigo-soft px-3.5 py-2.5 text-[13px] text-perigo",
        className,
      )}
    >
      <CircleAlert aria-hidden className="mt-px size-4 shrink-0" strokeWidth={1.8} />
      <p className="min-w-0 flex-1 leading-relaxed">{children}</p>
      {acao}
      {aoDispensar && (
        <button
          type="button"
          onClick={aoDispensar}
          aria-label="Dispensar aviso"
          className="-m-1 rounded-md p-1 opacity-70 transition-opacity hover:opacity-100"
        >
          <X aria-hidden className="size-4" />
        </button>
      )}
    </div>
  );
}
