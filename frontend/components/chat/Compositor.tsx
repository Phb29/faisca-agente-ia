"use client";

import { ArrowUp } from "lucide-react";
import { useId, useLayoutEffect, useState, type FormEvent, type KeyboardEvent, type RefObject } from "react";
import { cx } from "@/lib/cx";
import { Carregando } from "@/components/ui/Carregando";

type Props = {
  valor: string;
  aoMudar: (valor: string) => void;
  /** Rejeita quando o envio falha; aí o texto continua no campo. */
  aoEnviar: (texto: string) => Promise<void>;
  campo: RefObject<HTMLTextAreaElement | null>;
  /** Motivo para não aceitar mensagens agora (ex.: Aprovação Pendente). */
  bloqueio?: string | null;
  /** O assistente ainda está respondendo: dá para escrever, não para enviar. */
  ocupado?: boolean;
};

const ALTURA_MAXIMA = 192;

export function Compositor({ valor, aoMudar, aoEnviar, campo, bloqueio, ocupado = false }: Props) {
  const id = useId();
  const [enviando, setEnviando] = useState(false);
  const texto = valor.trim();
  const podeEnviar = Boolean(texto) && !bloqueio && !ocupado && !enviando;

  // A caixa cresce com o texto até a altura máxima e depois rola.
  useLayoutEffect(() => {
    const elemento = campo.current;
    if (!elemento) return;
    elemento.style.height = "auto";
    elemento.style.height = `${Math.min(elemento.scrollHeight, ALTURA_MAXIMA)}px`;
  }, [valor, campo]);

  async function enviar() {
    if (!podeEnviar) return;
    setEnviando(true);
    try {
      await aoEnviar(texto);
      aoMudar("");
    } catch {
      // o erro já aparece na tela; o texto fica para tentar de novo
    } finally {
      setEnviando(false);
    }
  }

  function aoSubmeter(evento: FormEvent) {
    evento.preventDefault();
    void enviar();
  }

  function aoTeclar(evento: KeyboardEvent<HTMLTextAreaElement>) {
    if (evento.key === "Enter" && !evento.shiftKey && !evento.nativeEvent.isComposing) {
      evento.preventDefault();
      void enviar();
    }
  }

  const dica = bloqueio ?? (ocupado ? "O assistente está respondendo…" : "Respostas geradas por IA e verificadas por guardrails.");

  return (
    <form onSubmit={aoSubmeter} className="mx-auto w-full max-w-[760px]">
      <div
        className={cx(
          "flex items-end gap-2 rounded-[22px] bg-surface p-2 pl-4 shadow-flutuante ring-1 ring-line transition-shadow",
          "focus-within:ring-[1.5px] focus-within:ring-ink/30",
          bloqueio && "bg-surface-2",
        )}
      >
        <label htmlFor={id} className="sr-only">
          Mensagem para o suporte
        </label>
        <textarea
          id={id}
          ref={campo}
          value={valor}
          rows={1}
          disabled={Boolean(bloqueio)}
          onChange={(evento) => aoMudar(evento.target.value)}
          onKeyDown={aoTeclar}
          placeholder={bloqueio ? "Aguardando o Atendente…" : "Escreva sua mensagem"}
          className="max-h-48 min-h-[40px] flex-1 resize-none bg-transparent py-2 text-[15px] leading-6 text-ink outline-none placeholder:text-muted disabled:cursor-not-allowed"
        />
        <button
          type="submit"
          disabled={!podeEnviar}
          aria-label="Enviar mensagem"
          className="flex size-10 shrink-0 items-center justify-center rounded-full bg-ink text-canvas transition-[transform,background-color] duration-150 hover:scale-[1.04] active:scale-95 disabled:scale-100 disabled:bg-canvas-2 disabled:text-muted"
        >
          {enviando ? <Carregando className="size-4" rotulo="Enviando" /> : <ArrowUp aria-hidden className="size-[18px]" strokeWidth={2} />}
        </button>
      </div>
      <p className="mt-2 flex items-center justify-between gap-4 px-3 text-[11.5px] text-muted">
        <span className="truncate">{dica}</span>
        <span className="hidden shrink-0 items-center gap-1 sm:flex">
          <Tecla>Enter</Tecla> envia · <Tecla>Shift</Tecla>+<Tecla>Enter</Tecla> quebra linha
        </span>
      </p>
    </form>
  );
}

function Tecla({ children }: { children: string }) {
  return (
    <kbd className="rounded-[5px] bg-surface px-1.5 py-px font-mono text-[10px] text-ink-2 ring-1 ring-line">
      {children}
    </kbd>
  );
}
