"use client";

import { useEffect, useState } from "react";
import { listarClientes, type Cliente } from "@/lib/api";
import { gerarId } from "@/lib/local";

export type ClienteEscolhido = { id: string; nome: string };

type Props = {
  aoEscolher: (cliente: ClienteEscolhido) => void;
};

export function SeletorDeCliente({ aoEscolher }: Props) {
  const [clientes, setClientes] = useState<Cliente[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let ativo = true;
    listarClientes()
      .then((lista) => ativo && setClientes(lista))
      .catch((e: Error) => ativo && setErro(e.message));
    return () => {
      ativo = false;
    };
  }, []);

  function entrarComoNovo() {
    const id = gerarId("cli_");
    aoEscolher({ id, nome: "Cliente novo" });
  }

  return (
    <div className="mx-auto w-full max-w-lg px-4 py-12">
      <div className="rounded-2xl border border-stone-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold">Quem está falando?</h1>
        <p className="mt-1 text-sm text-stone-600">
          Escolha um Cliente fictício para conversar com o suporte da Ampère.
        </p>

        {erro && (
          <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            Não foi possível carregar os Clientes: {erro}
          </p>
        )}

        <ul className="mt-5 space-y-2">
          {clientes === null && !erro && (
            <li className="text-sm text-stone-500">Carregando Clientes…</li>
          )}
          {clientes?.map((cliente) => (
            <li key={cliente.id}>
              <button
                type="button"
                onClick={() => aoEscolher({ id: cliente.id, nome: cliente.nome })}
                className="flex w-full items-center justify-between rounded-xl border border-stone-200 px-4 py-3 text-left transition hover:border-amber-400 hover:bg-amber-50"
              >
                <span>
                  <span className="block font-medium">{cliente.nome}</span>
                  <span className="block text-xs text-stone-500">
                    {cliente.email}
                  </span>
                </span>
                <span className="text-xs text-stone-400">{cliente.id}</span>
              </button>
            </li>
          ))}
        </ul>

        <button
          type="button"
          onClick={entrarComoNovo}
          className="mt-5 w-full rounded-xl bg-stone-900 px-4 py-3 text-sm font-medium text-white transition hover:bg-stone-700"
        >
          Entrar como Cliente novo
        </button>
      </div>
    </div>
  );
}
