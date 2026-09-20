"use client";

import type { Conversa, StatusDaConversa } from "@/lib/api";
import { formatarData } from "@/lib/local";

const ROTULO_DO_STATUS: Record<StatusDaConversa, string> = {
  aberta: "Aberta",
  aprovacao_pendente: "Aprovação Pendente",
  escalada: "Escalada",
  resolvida: "Resolvida",
};

const CLASSE_DO_STATUS: Record<StatusDaConversa, string> = {
  aberta: "bg-sky-100 text-sky-800",
  aprovacao_pendente: "bg-amber-100 text-amber-800",
  escalada: "bg-red-100 text-red-800",
  resolvida: "bg-emerald-100 text-emerald-800",
};

export function BadgeDeStatus({ status }: { status: StatusDaConversa }) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${CLASSE_DO_STATUS[status] ?? "bg-stone-100 text-stone-700"}`}
    >
      {ROTULO_DO_STATUS[status] ?? status}
    </span>
  );
}

type Props = {
  conversas: Conversa[];
  conversaAtivaId: string | null;
  carregando: boolean;
  aoSelecionar: (id: string) => void;
  aoCriar: () => void;
};

export function ListaDeConversas({
  conversas,
  conversaAtivaId,
  carregando,
  aoSelecionar,
  aoCriar,
}: Props) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-3 py-3">
        <h2 className="text-sm font-semibold text-stone-700">Conversas</h2>
        <button
          type="button"
          onClick={aoCriar}
          className="rounded-lg bg-amber-400 px-3 py-1.5 text-xs font-medium text-stone-900 transition hover:bg-amber-300"
        >
          Nova Conversa
        </button>
      </div>
      <ul className="flex-1 space-y-1 overflow-y-auto px-2 pb-3">
        {carregando && conversas.length === 0 && (
          <li className="px-2 py-2 text-xs text-stone-500">Carregando…</li>
        )}
        {!carregando && conversas.length === 0 && (
          <li className="px-2 py-2 text-xs text-stone-500">
            Nenhuma Conversa ainda. Crie uma para começar.
          </li>
        )}
        {conversas.map((conversa) => {
          const ativa = conversa.id === conversaAtivaId;
          return (
            <li key={conversa.id}>
              <button
                type="button"
                onClick={() => aoSelecionar(conversa.id)}
                className={`w-full rounded-lg px-3 py-2 text-left transition ${
                  ativa
                    ? "bg-white shadow-sm ring-1 ring-stone-200"
                    : "hover:bg-stone-100"
                }`}
              >
                <span className="block truncate text-sm font-medium text-stone-800">
                  {conversa.titulo || `Conversa de ${formatarData(conversa.criada_em)}`}
                </span>
                <span className="mt-1 flex items-center justify-between gap-2">
                  <BadgeDeStatus status={conversa.status} />
                  <span className="text-[11px] text-stone-400">
                    {formatarData(conversa.atualizada_em)}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
