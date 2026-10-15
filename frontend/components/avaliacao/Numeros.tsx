import { cx } from "@/lib/cx";
import { Esqueleto } from "@/components/ui/Vazio";

export type Numero = {
  rotulo: string;
  valor: string;
  /** Unidade pequena ao lado do número ("%", "/25"). */
  sufixo?: string;
  detalhe: string;
};

const GRADE_BASE = "grid grid-cols-1 gap-px overflow-hidden rounded-2xl bg-line shadow-suave ring-1 ring-line";

/** A faixa de números de destaque, grande o bastante para o telão. Enquanto carrega, o
 * esqueleto fica fora do `<dl>`: `dt`/`dd` são o único conteúdo válido dentro dele. */
export function Numeros({ itens }: { itens: Numero[] | null }) {
  if (!itens) {
    return (
      <div className={cx(GRADE_BASE, "sm:grid-cols-2 lg:grid-cols-4")}>
        {Array.from({ length: 4 }, (_, indice) => (
          <div key={indice} className="space-y-3 bg-surface p-5 sm:p-6">
            <Esqueleto className="h-3 w-24" />
            <Esqueleto className="h-10 w-20" />
            <Esqueleto className="h-3 w-36" />
          </div>
        ))}
      </div>
    );
  }
  return (
    <dl className={cx(GRADE_BASE, itens.length === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2 lg:grid-cols-4")}>
      {itens.map((item) => (
        <div key={item.rotulo} className="bg-surface p-5 sm:p-6">
          <dt className="sobretitulo">{item.rotulo}</dt>
          <dd className="mt-3 font-display text-[clamp(34px,3.2vw,46px)] leading-none font-semibold tracking-[-0.04em] tabular-nums">
            {item.valor}
            {item.sufixo && (
              <span className="ml-0.5 text-[0.42em] font-medium tracking-normal text-muted">
                {item.sufixo}
              </span>
            )}
          </dd>
          <dd className="mt-2 text-[13px] text-muted">{item.detalhe}</dd>
        </div>
      ))}
    </dl>
  );
}
