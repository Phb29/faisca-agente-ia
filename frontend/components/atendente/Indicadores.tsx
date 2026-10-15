import type { Aprovacao, Ticket } from "@/lib/api";
import { cx } from "@/lib/cx";
import { formatarReais, formatarRelativo } from "@/lib/formatos";
import { Esqueleto } from "@/components/ui/Vazio";

type Indicador = { rotulo: string; valor: string; detalhe: string; destaque?: "alerta" | "perigo" };

const UM_DIA_MS = 86_400_000;

function calcular(aprovacoes: Aprovacao[], tickets: Ticket[]): Indicador[] {
  const aguardando = aprovacoes.reduce((total, a) => total + a.valor, 0);
  const maisAntiga = aprovacoes.reduce<string | null>(
    (antiga, a) => (!antiga || a.criada_em < antiga ? a.criada_em : antiga),
    null,
  );
  const altas = tickets.filter((t) => t.prioridade === "alta").length;
  const ultimoDia = tickets.filter((t) => Date.now() - new Date(t.criado_em).getTime() < UM_DIA_MS).length;

  return [
    {
      rotulo: "Aprovações pendentes",
      valor: String(aprovacoes.length),
      detalhe: aprovacoes.length ? `${formatarReais(aguardando)} aguardando` : "Fila vazia",
      destaque: aprovacoes.length ? "alerta" : undefined,
    },
    {
      rotulo: "Espera mais longa",
      valor: maisAntiga ? formatarRelativo(maisAntiga).replace(/^há /, "") : "—",
      detalhe: maisAntiga ? "desde a Aprovação mais antiga" : "Nenhum Cliente esperando",
    },
    {
      rotulo: "Tickets",
      valor: String(tickets.length),
      detalhe: `${ultimoDia} nas últimas 24 h`,
    },
    {
      rotulo: "Alta prioridade",
      valor: String(altas),
      detalhe: altas ? "Tickets pedindo atenção" : "Nada urgente",
      destaque: altas ? "perigo" : undefined,
    },
  ];
}

type Props = { aprovacoes: Aprovacao[] | null; tickets: Ticket[] | null };

export function Indicadores({ aprovacoes, tickets }: Props) {
  const carregando = aprovacoes === null || tickets === null;
  const indicadores = carregando ? null : calcular(aprovacoes, tickets);

  return (
    <dl className="grid grid-cols-2 overflow-hidden rounded-2xl bg-surface shadow-suave ring-1 ring-line lg:grid-cols-4">
      {(indicadores ?? Array.from({ length: 4 }, () => null)).map((indicador, indice) => (
        <div
          key={indicador?.rotulo ?? indice}
          className={cx(
            "relative p-5 sm:p-6",
            indice % 2 === 1 && "border-l border-line",
            indice >= 2 && "border-t border-line lg:border-t-0",
            indice === 2 && "lg:border-l",
          )}
        >
          {indicador ? (
            <>
              <dt className="sobretitulo flex items-center gap-2">
                {indicador.destaque && (
                  <span
                    aria-hidden
                    className={cx("size-1.5 rounded-full", indicador.destaque === "alerta" ? "bg-alerta" : "bg-perigo")}
                  />
                )}
                {indicador.rotulo}
              </dt>
              <dd className="mt-3 font-display text-[34px] leading-none font-semibold tracking-[-0.035em] tabular-nums">{indicador.valor}</dd>
              <dd className="mt-2 truncate text-[12.5px] text-muted">{indicador.detalhe}</dd>
            </>
          ) : (
            <div className="space-y-3">
              <Esqueleto className="h-3 w-24" />
              <Esqueleto className="h-9 w-14" />
              <Esqueleto className="h-3 w-32" />
            </div>
          )}
        </div>
      ))}
    </dl>
  );
}
