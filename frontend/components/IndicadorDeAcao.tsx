"use client";

import type { NomeDaAcao } from "@/lib/sse";

const TEXTO_DA_ACAO: Record<NomeDaAcao, string> = {
  consultar_pedido: "Consultando pedido…",
  consultar_base_de_conhecimento: "Buscando política…",
  emitir_reembolso: "Emitindo reembolso…",
  abrir_ticket: "Abrindo ticket…",
};

export function IndicadorDeAcao({ acao }: { acao: NomeDaAcao | null }) {
  if (!acao) return null;
  return (
    <div className="flex items-center gap-2 px-4 py-1.5 text-xs text-stone-600">
      <span className="h-2 w-2 animate-pulse rounded-full bg-amber-400" />
      {TEXTO_DA_ACAO[acao] ?? `Executando ${acao}…`}
    </div>
  );
}
