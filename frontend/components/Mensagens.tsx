"use client";

import { useEffect, useRef } from "react";
import type { Mensagem } from "@/lib/api";
import { formatarData } from "@/lib/local";

type Props = {
  mensagens: Mensagem[];
  emConstrucao: string | null;
  aguardandoResposta: boolean;
  carregando: boolean;
};

function Balao({
  papel,
  conteudo,
  rodape,
  digitando,
}: {
  papel: "cliente" | "assistente";
  conteudo: string;
  rodape?: string;
  digitando?: boolean;
}) {
  const doCliente = papel === "cliente";
  return (
    <div className={`flex ${doCliente ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap shadow-sm ${
          doCliente
            ? "rounded-br-sm bg-stone-900 text-white"
            : "rounded-bl-sm border border-stone-200 bg-white text-stone-800"
        }`}
      >
        {conteudo}
        {digitando && (
          <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-stone-400 align-middle" />
        )}
        {rodape && (
          <span
            className={`mt-1 block text-[10px] ${doCliente ? "text-stone-300" : "text-stone-400"}`}
          >
            {rodape}
          </span>
        )}
      </div>
    </div>
  );
}

export function Mensagens({
  mensagens,
  emConstrucao,
  aguardandoResposta,
  carregando,
}: Props) {
  const fim = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fim.current?.scrollIntoView({ block: "end" });
  }, [mensagens, emConstrucao, aguardandoResposta]);

  return (
    <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
      {carregando && mensagens.length === 0 && (
        <p className="text-center text-xs text-stone-500">Carregando mensagens…</p>
      )}
      {!carregando && mensagens.length === 0 && !emConstrucao && (
        <p className="mt-10 text-center text-sm text-stone-500">
          Envie uma mensagem para começar. Pergunte sobre trocas, frete,
          garantia ou o status de um Pedido.
        </p>
      )}
      {mensagens.map((mensagem) => (
        <Balao
          key={mensagem.id}
          papel={mensagem.papel}
          conteudo={mensagem.conteudo}
          rodape={formatarData(mensagem.criada_em)}
        />
      ))}
      {emConstrucao !== null && (
        <Balao papel="assistente" conteudo={emConstrucao} digitando />
      )}
      {aguardandoResposta && emConstrucao === null && (
        <div className="flex justify-start">
          <div className="rounded-2xl rounded-bl-sm border border-stone-200 bg-white px-4 py-3">
            <span className="flex gap-1">
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-stone-400 [animation-delay:-0.3s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-stone-400 [animation-delay:-0.15s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-stone-400" />
            </span>
          </div>
        </div>
      )}
      <div ref={fim} />
    </div>
  );
}
