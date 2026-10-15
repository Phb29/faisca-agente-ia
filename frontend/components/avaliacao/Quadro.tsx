import type { ReactNode } from "react";

type Props = {
  id: string;
  titulo: string;
  descricao: string;
  children: ReactNode;
};

/** Um bloco de uma aba: título, uma frase do que ele mostra e o conteúdo. */
export function Quadro({ id, titulo, descricao, children }: Props) {
  return (
    <section aria-labelledby={id} className="min-w-0 rounded-2xl bg-surface p-5 shadow-suave ring-1 ring-line">
      <div className="flex items-end justify-between gap-4">
        <div className="min-w-0">
          <h2 id={id} className="text-[15px] font-semibold tracking-[-0.01em]">
            {titulo}
          </h2>
          <p className="mt-1 text-[12.5px] leading-relaxed text-muted">{descricao}</p>
        </div>
      </div>
      {children}
    </section>
  );
}
