"use client";

import { useEffect, useState } from "react";
import {
  lerMemoriaProcedural,
  listarClientes,
  salvarMemoriaProcedural,
  type Cliente,
} from "@/lib/api";

type Props = {
  token: string;
  aoErro: (erro: unknown) => void;
};

export function MemoriaProcedural({ token, aoErro }: Props) {
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [clienteId, setClienteId] = useState("");
  const [texto, setTexto] = useState("");
  const [textoSalvo, setTextoSalvo] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    let ativo = true;
    listarClientes()
      .then((lista) => {
        if (!ativo) return;
        setClientes(lista);
        if (lista.length > 0) setClienteId((atual) => atual || lista[0].id);
      })
      .catch(aoErro);
    return () => {
      ativo = false;
    };
  }, [aoErro]);

  useEffect(() => {
    if (!clienteId) return;
    let ativo = true;
    setCarregando(true);
    setAviso(null);
    lerMemoriaProcedural(token, clienteId)
      .then(({ texto: atual }) => {
        if (!ativo) return;
        setTexto(atual ?? "");
        setTextoSalvo(atual ?? "");
      })
      .catch(aoErro)
      .finally(() => ativo && setCarregando(false));
    return () => {
      ativo = false;
    };
  }, [token, clienteId, aoErro]);

  async function salvar() {
    if (!clienteId) return;
    setSalvando(true);
    setAviso(null);
    try {
      const resposta = await salvarMemoriaProcedural(token, clienteId, texto);
      setTexto(resposta.texto ?? texto);
      setTextoSalvo(resposta.texto ?? texto);
      setAviso("Memória Procedural salva.");
    } catch (e) {
      aoErro(e);
    } finally {
      setSalvando(false);
    }
  }

  const alterado = texto !== textoSalvo;

  return (
    <section className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
      <h2 className="text-base font-semibold">Memória Procedural</h2>
      <p className="mt-1 text-xs text-stone-500">
        Instruções de como o chatbot deve atender este Cliente nas próximas
        Conversas. Exemplo: &ldquo;responder em tom formal&rdquo;, &ldquo;não
        oferecer cupom&rdquo;.
      </p>

      <label className="mt-4 block text-xs font-medium text-stone-600">
        Cliente
        <select
          value={clienteId}
          onChange={(e) => setClienteId(e.target.value)}
          className="mt-1 w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-200"
        >
          {clientes.length === 0 && <option value="">Carregando Clientes…</option>}
          {clientes.map((cliente) => (
            <option key={cliente.id} value={cliente.id}>
              {cliente.nome} ({cliente.id})
            </option>
          ))}
        </select>
      </label>

      <textarea
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        disabled={carregando || !clienteId}
        rows={6}
        placeholder={carregando ? "Carregando…" : "Sem instruções para este Cliente."}
        className="mt-3 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-200 disabled:bg-stone-100"
      />

      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={() => void salvar()}
          disabled={salvando || carregando || !clienteId || !alterado}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:cursor-not-allowed disabled:bg-stone-300"
        >
          {salvando ? "Salvando…" : "Salvar"}
        </button>
        {aviso && <span className="text-xs text-emerald-700">{aviso}</span>}
        {alterado && !aviso && (
          <span className="text-xs text-stone-500">Alterações não salvas</span>
        )}
      </div>
    </section>
  );
}
