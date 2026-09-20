"use client";

import type { EventoApprovalRequired } from "@/lib/sse";
import { formatarReais } from "@/lib/local";

export function AvisoDeAprovacao({
  aprovacao,
}: {
  aprovacao: EventoApprovalRequired | null;
}) {
  if (!aprovacao) return null;
  return (
    <div className="border-y border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-900">
      <span className="font-medium">Aguardando aprovação de um Atendente.</span>{" "}
      <span className="text-amber-800">
        Reembolso de {formatarReais(aprovacao.valor)} do Pedido{" "}
        {aprovacao.pedido_id}. A resposta chega nesta mesma Conversa assim que
        o Atendente decidir.
      </span>
    </div>
  );
}
