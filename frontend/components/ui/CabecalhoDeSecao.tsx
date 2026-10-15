import type { ReactNode } from "react";

type Props = {
  id: string;
  titulo: string;
  descricao?: string;
  contagem?: number;
  /** Controles à direita do título (filtros, ações). */
  children?: ReactNode;
};

export function CabecalhoDeSecao({ id, titulo, descricao, contagem, children }: Props) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h2 id={id} className="flex items-baseline gap-2.5 text-[17px] font-semibold tracking-[-0.01em]">
          {titulo}
          {contagem !== undefined && (
            <span className="font-mono text-[12px] font-normal text-muted">{contagem}</span>
          )}
        </h2>
        {descricao && <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-muted">{descricao}</p>}
      </div>
      {children}
    </div>
  );
}
