"use client";

import Link from "next/link";
import { ArrowLeft, KeyRound } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { ErroDaApi, listarAprovacoes, mensagemDeErro } from "@/lib/api";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { Marca } from "@/components/ui/Marca";

type Props = {
  /** Motivo de ter voltado ao login (ex.: token expirado). */
  aviso: string | null;
  aoEntrar: (token: string) => void;
};

/** O token é conferido na hora contra a API, antes de ser guardado. */
export function Login({ aviso, aoEntrar }: Props) {
  const id = useId();
  const [token, setToken] = useState("");
  const [verificando, setVerificando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function entrar(evento: FormEvent) {
    evento.preventDefault();
    const valor = token.trim();
    if (!valor) return;
    setVerificando(true);
    setErro(null);
    try {
      await listarAprovacoes(valor);
      aoEntrar(valor);
    } catch (e) {
      setErro(e instanceof ErroDaApi && e.status === 401 ? "Token inválido. Confira e tente de novo." : mensagemDeErro(e));
    } finally {
      setVerificando(false);
    }
  }

  const mensagem = erro ?? aviso;

  return (
    <div className="grid min-h-dvh place-items-center px-5 py-12">
      <div className="w-full max-w-[400px]">
        <form
          onSubmit={entrar}
          className="animate-surgir rounded-3xl bg-surface p-8 shadow-flutuante ring-1 ring-line"
        >
          <Marca tamanho="lg" />
          <h1 className="mt-6 font-display text-[30px] leading-[1.1] font-semibold tracking-[-0.03em]">Central do Atendente</h1>
          <p className="mt-2 text-[14.5px] leading-relaxed text-muted">
            Aprovações de Reembolso, Tickets e a Memória Procedural de cada Cliente.
          </p>

          {mensagem && <Aviso className="mt-5">{mensagem}</Aviso>}

          <label htmlFor={id} className="mt-6 block text-[12.5px] font-medium text-ink-2">
            Token de acesso
          </label>
          <div className="relative mt-1.5">
            <KeyRound
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted"
              strokeWidth={1.7}
            />
            <input
              id={id}
              type="password"
              value={token}
              onChange={(evento) => setToken(evento.target.value)}
              autoComplete="current-password"
              autoFocus
              className="h-11 w-full rounded-xl bg-surface-2 pr-3 pl-10 text-[14.5px] ring-1 ring-line transition outline-none ring-inset placeholder:text-muted focus:bg-surface focus:ring-[1.5px] focus:ring-ink/40"
              placeholder="••••••••••"
            />
          </div>

          <Botao type="submit" tamanho="lg" className="mt-5 w-full" carregando={verificando} disabled={!token.trim()}>
            Entrar
          </Botao>

          <p className="mt-5 text-center text-[12px] leading-relaxed text-muted">
            O token é o <code className="font-mono text-ink-2">ATENDENTE_TOKEN</code> configurado na API.
          </p>
        </form>

        <Link
          href="/"
          className="mt-6 flex items-center justify-center gap-1.5 text-[13px] text-muted transition-colors hover:text-ink"
        >
          <ArrowLeft aria-hidden className="size-3.5" /> Voltar ao chat
        </Link>
      </div>
    </div>
  );
}
