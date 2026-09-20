"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ErroDaApi } from "@/lib/api";
import {
  CHAVE_TOKEN_ATENDENTE,
  apagarLocal,
  gravarLocal,
  lerLocal,
} from "@/lib/local";
import { AprovacoesPendentes } from "@/components/AprovacoesPendentes";
import { Tickets } from "@/components/Tickets";
import { MemoriaProcedural } from "@/components/MemoriaProcedural";

export default function TelaDoAtendente() {
  const [hidratado, setHidratado] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [tokenDigitado, setTokenDigitado] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setToken(lerLocal<string>(CHAVE_TOKEN_ATENDENTE));
    setHidratado(true);
  }, []);

  const sair = useCallback((mensagem?: string) => {
    apagarLocal(CHAVE_TOKEN_ATENDENTE);
    setToken(null);
    setErro(mensagem ?? null);
  }, []);

  // Erros vindos dos componentes: 401 limpa o token e pede de novo.
  const aoErro = useCallback(
    (e: unknown) => {
      if (e instanceof ErroDaApi && e.status === 401) {
        sair("Token inválido ou expirado. Informe o token de novo.");
        return;
      }
      setErro(e instanceof Error ? e.message : String(e));
    },
    [sair],
  );

  function entrar(evento: FormEvent) {
    evento.preventDefault();
    const valor = tokenDigitado.trim();
    if (!valor) return;
    gravarLocal(CHAVE_TOKEN_ATENDENTE, valor);
    setToken(valor);
    setTokenDigitado("");
    setErro(null);
  }

  if (!hidratado) return null;

  if (!token) {
    return (
      <div className="mx-auto w-full max-w-md px-4 py-12">
        <form
          onSubmit={entrar}
          className="rounded-2xl border border-stone-200 bg-white p-6 shadow-sm"
        >
          <h1 className="text-xl font-semibold">Tela do Atendente</h1>
          <p className="mt-1 text-sm text-stone-600">
            Informe o token de Atendente para ver Aprovações Pendentes, Tickets e
            a Memória Procedural dos Clientes.
          </p>
          {erro && (
            <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {erro}
            </p>
          )}
          <input
            type="password"
            value={tokenDigitado}
            onChange={(e) => setTokenDigitado(e.target.value)}
            placeholder="Token"
            autoComplete="off"
            className="mt-4 w-full rounded-xl border border-stone-300 px-3 py-2.5 text-sm outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-200"
          />
          <button
            type="submit"
            disabled={!tokenDigitado.trim()}
            className="mt-4 w-full rounded-xl bg-stone-900 px-4 py-3 text-sm font-medium text-white hover:bg-stone-700 disabled:bg-stone-300"
          >
            Entrar
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Tela do Atendente</h1>
        <button
          type="button"
          onClick={() => sair()}
          className="text-xs text-stone-500 underline-offset-2 hover:text-stone-900 hover:underline"
        >
          Sair
        </button>
      </div>

      {erro && (
        <div className="mt-4 flex items-start justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          <span>{erro}</span>
          <button type="button" onClick={() => setErro(null)} className="text-xs underline">
            fechar
          </button>
        </div>
      )}

      <div className="mt-6 space-y-6">
        <AprovacoesPendentes token={token} aoErro={aoErro} />
        <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
          <Tickets token={token} aoErro={aoErro} />
          <MemoriaProcedural token={token} aoErro={aoErro} />
        </div>
      </div>
    </div>
  );
}
