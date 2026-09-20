"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";

type Props = {
  desabilitada: boolean;
  aoEnviar: (conteudo: string) => Promise<void> | void;
};

export function CaixaDeEnvio({ desabilitada, aoEnviar }: Props) {
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function enviar() {
    const conteudo = texto.trim();
    if (!conteudo || desabilitada || enviando) return;
    setEnviando(true);
    try {
      await aoEnviar(conteudo);
      setTexto("");
    } finally {
      setEnviando(false);
    }
  }

  function aoSubmeter(evento: FormEvent) {
    evento.preventDefault();
    void enviar();
  }

  function aoTeclar(evento: KeyboardEvent<HTMLTextAreaElement>) {
    if (evento.key === "Enter" && !evento.shiftKey) {
      evento.preventDefault();
      void enviar();
    }
  }

  return (
    <form
      onSubmit={aoSubmeter}
      className="flex items-end gap-2 border-t border-stone-200 bg-white px-4 py-3"
    >
      <textarea
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        onKeyDown={aoTeclar}
        rows={1}
        disabled={desabilitada}
        placeholder={
          desabilitada
            ? "Selecione ou crie uma Conversa para enviar mensagens"
            : "Escreva sua mensagem (Enter envia, Shift+Enter quebra linha)"
        }
        className="max-h-40 min-h-[44px] flex-1 resize-y rounded-xl border border-stone-300 px-3 py-2.5 text-sm outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-200 disabled:bg-stone-100"
      />
      <button
        type="submit"
        disabled={desabilitada || enviando || !texto.trim()}
        className="h-[44px] rounded-xl bg-stone-900 px-4 text-sm font-medium text-white transition hover:bg-stone-700 disabled:cursor-not-allowed disabled:bg-stone-300"
      >
        {enviando ? "Enviando…" : "Enviar"}
      </button>
    </form>
  );
}
