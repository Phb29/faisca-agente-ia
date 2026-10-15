import { cx } from "@/lib/cx";
import { Esqueleto } from "@/components/ui/Vazio";

export type Numero = {
  rotulo: string;
  valor: string;
  /** Unidade pequena ao lado do número ("%", "/25"). */
  sufixo?: string;
  detalhe: string;
};

/** A faixa de números de destaque, grande o bastante para o telão. */
export function Numeros({ itens }: { itens: Numero[] | null }) {
  const lista = itens ?? Array.from({ length: 4 }, () => null);
  return (
    <dl
      className={cx(
        "grid grid-cols-1 gap-px overflow-hidden rounded-2xl bg-line shadow-suave ring-1 ring-line",
        lista.length === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2 lg:grid-cols-4",
      )}
    >
      {lista.map((item, indice) => (
        <div key={item?.rotulo ?? indice} className="bg-surface p-5 sm:p-6">
          {item ? (
            <>
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
            </>
          ) : (
            <div className="space-y-3">
              <Esqueleto className="h-3 w-24" />
              <Esqueleto className="h-10 w-20" />
              <Esqueleto className="h-3 w-36" />
            </div>
          )}
        </div>
      ))}
    </dl>
  );
}
