"use client";

import { useCallback, useEffect, useState } from "react";
import {
  aprovarReembolso,
  listarAprovacoes,
  rejeitarReembolso,
  type Aprovacao,
} from "@/lib/api";
import { formatarData, formatarPorcentagem, formatarReais } from "@/lib/local";

const INTERVALO_MS = 5000;

type Props = {
  token: string;
  aoErro: (erro: unknown) => void;
};

export function AprovacoesPendentes({ token, aoErro }: Props) {
  const [aprovacoes, setAprovacoes] = useState<Aprovacao[] | null>(null);
  const [decididas, setDecididas] = useState<Set<string>>(new Set());
  const [retomadas, setRetomadas] = useState<string[]>([]);
  const [motivos, setMotivos] = useState<Record<string, string>>({});
  const [rejeitando, setRejeitando] = useState<string | null>(null);
  const [ocupada, setOcupada] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      setAprovacoes(await listarAprovacoes(token));
    } catch (e) {
      aoErro(e);
    }
  }, [token, aoErro]);

  useEffect(() => {
    void carregar();
    const timer = setInterval(() => void carregar(), INTERVALO_MS);
    return () => clearInterval(timer);
  }, [carregar]);

  function marcarDecidida(id: string) {
    setDecididas((atual) => new Set(atual).add(id));
    setRetomadas((atual) => [...atual, id]);
    setTimeout(() => {
      setRetomadas((atual) => atual.filter((x) => x !== id));
    }, 6000);
  }

  async function aprovar(id: string) {
    setOcupada(id);
    try {
      await aprovarReembolso(token, id);
      marcarDecidida(id);
    } catch (e) {
      aoErro(e);
    } finally {
      setOcupada(null);
    }
  }

  async function rejeitar(id: string) {
    setOcupada(id);
    try {
      await rejeitarReembolso(token, id, motivos[id]?.trim() || undefined);
      marcarDecidida(id);
      setRejeitando(null);
    } catch (e) {
      aoErro(e);
    } finally {
      setOcupada(null);
    }
  }

  const visiveis = (aprovacoes ?? []).filter((a) => !decididas.has(a.id));

  return (
    <section className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Aprovações Pendentes</h2>
        <span className="text-xs text-stone-500">
          {aprovacoes === null ? "carregando…" : `${visiveis.length} pendente(s)`}
        </span>
      </div>

      {retomadas.length > 0 && (
        <p className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          Conversa retomada. O Cliente receberá a resposta no chat.
        </p>
      )}

      {aprovacoes !== null && visiveis.length === 0 && (
        <p className="mt-3 text-sm text-stone-500">
          Nenhum Reembolso aguardando decisão.
        </p>
      )}

      <ul className="mt-4 grid gap-4 md:grid-cols-2">
        {visiveis.map((aprovacao) => {
          const emRejeicao = rejeitando === aprovacao.id;
          const travada = ocupada === aprovacao.id;
          return (
            <li
              key={aprovacao.id}
              className="flex flex-col rounded-xl border border-amber-200 bg-amber-50/40 p-4"
            >
              <p className="text-sm text-stone-800">{aprovacao.resumo}</p>
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <dt className="text-stone-500">Valor</dt>
                <dd className="font-medium">{formatarReais(aprovacao.valor)}</dd>
                <dt className="text-stone-500">Probabilidade do Gate</dt>
                <dd className="font-medium">
                  {formatarPorcentagem(aprovacao.probabilidade)}
                </dd>
                <dt className="text-stone-500">Cliente</dt>
                <dd className="truncate">{aprovacao.cliente_id}</dd>
                <dt className="text-stone-500">Pedido</dt>
                <dd className="truncate">{aprovacao.pedido_id}</dd>
                <dt className="text-stone-500">Conversa</dt>
                <dd className="truncate">{aprovacao.conversa_id}</dd>
                <dt className="text-stone-500">Criada em</dt>
                <dd>{formatarData(aprovacao.criada_em)}</dd>
              </dl>

              {emRejeicao && (
                <textarea
                  value={motivos[aprovacao.id] ?? ""}
                  onChange={(e) =>
                    setMotivos((m) => ({ ...m, [aprovacao.id]: e.target.value }))
                  }
                  rows={2}
                  placeholder="Motivo (opcional), enviado ao Cliente"
                  className="mt-3 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-200"
                />
              )}

              <div className="mt-3 flex flex-wrap gap-2">
                {!emRejeicao ? (
                  <>
                    <button
                      type="button"
                      disabled={travada}
                      onClick={() => void aprovar(aprovacao.id)}
                      className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                    >
                      Aprovar
                    </button>
                    <button
                      type="button"
                      disabled={travada}
                      onClick={() => setRejeitando(aprovacao.id)}
                      className="rounded-lg border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                    >
                      Rejeitar
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      disabled={travada}
                      onClick={() => void rejeitar(aprovacao.id)}
                      className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
                    >
                      Confirmar rejeição
                    </button>
                    <button
                      type="button"
                      disabled={travada}
                      onClick={() => setRejeitando(null)}
                      className="rounded-lg border border-stone-300 px-3 py-1.5 text-sm text-stone-700 hover:bg-stone-100"
                    >
                      Cancelar
                    </button>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
