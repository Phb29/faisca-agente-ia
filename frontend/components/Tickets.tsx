"use client";

import { useCallback, useEffect, useState } from "react";
import {
  lerConversaDoTicket,
  listarTickets,
  type ConversaDoTicket,
  type Ticket,
} from "@/lib/api";
import { formatarData } from "@/lib/local";

const INTERVALO_MS = 5000;

type Props = {
  token: string;
  aoErro: (erro: unknown) => void;
};

export function Tickets({ token, aoErro }: Props) {
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [aberto, setAberto] = useState<ConversaDoTicket | null>(null);
  const [carregandoConversa, setCarregandoConversa] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      setTickets(await listarTickets(token));
    } catch (e) {
      aoErro(e);
    }
  }, [token, aoErro]);

  useEffect(() => {
    void carregar();
    const timer = setInterval(() => void carregar(), INTERVALO_MS);
    return () => clearInterval(timer);
  }, [carregar]);

  async function verConversa(ticketId: string) {
    setCarregandoConversa(ticketId);
    try {
      setAberto(await lerConversaDoTicket(token, ticketId));
    } catch (e) {
      aoErro(e);
    } finally {
      setCarregandoConversa(null);
    }
  }

  return (
    <section className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Tickets</h2>
        <span className="text-xs text-stone-500">
          {tickets === null ? "carregando…" : `${tickets.length} ticket(s)`}
        </span>
      </div>

      {tickets !== null && tickets.length === 0 && (
        <p className="mt-3 text-sm text-stone-500">Nenhum Ticket aberto.</p>
      )}

      {tickets && tickets.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-stone-500">
              <tr className="border-b border-stone-200">
                <th className="py-2 pr-3 font-medium">Resumo</th>
                <th className="py-2 pr-3 font-medium">Categoria</th>
                <th className="py-2 pr-3 font-medium">Prioridade</th>
                <th className="py-2 pr-3 font-medium">Cliente</th>
                <th className="py-2 pr-3 font-medium">Criado em</th>
                <th className="py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {tickets.map((ticket) => (
                <tr key={ticket.id} className="border-b border-stone-100 align-top">
                  <td className="max-w-md py-2 pr-3">{ticket.resumo}</td>
                  <td className="py-2 pr-3">
                    <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs">
                      {ticket.categoria}
                    </span>
                  </td>
                  <td className="py-2 pr-3">
                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-900">
                      {ticket.prioridade}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-xs text-stone-600">{ticket.cliente_id}</td>
                  <td className="py-2 pr-3 text-xs text-stone-600 whitespace-nowrap">
                    {formatarData(ticket.criado_em)}
                  </td>
                  <td className="py-2 text-right">
                    <button
                      type="button"
                      disabled={carregandoConversa === ticket.id}
                      onClick={() => void verConversa(ticket.id)}
                      className="rounded-lg border border-stone-300 px-3 py-1 text-xs font-medium hover:bg-stone-100 disabled:opacity-50"
                    >
                      {carregandoConversa === ticket.id ? "Abrindo…" : "Ver Conversa"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {aberto && (
        <div
          className="fixed inset-0 z-20 flex justify-end bg-stone-900/30"
          onClick={() => setAberto(null)}
        >
          <div
            className="flex h-full w-full max-w-xl flex-col bg-white shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3 border-b border-stone-200 px-5 py-4">
              <div>
                <h3 className="text-sm font-semibold">Conversa do Ticket</h3>
                <p className="mt-1 text-xs text-stone-600">{aberto.ticket.resumo}</p>
                <p className="mt-1 text-[11px] text-stone-500">
                  {aberto.ticket.categoria} · {aberto.ticket.prioridade} · Cliente{" "}
                  {aberto.ticket.cliente_id}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setAberto(null)}
                className="rounded-lg border border-stone-300 px-2 py-1 text-xs hover:bg-stone-100"
              >
                Fechar
              </button>
            </div>
            <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
              {aberto.mensagens.length === 0 && (
                <p className="text-sm text-stone-500">Sem mensagens.</p>
              )}
              {aberto.mensagens.map((mensagem) => (
                <div
                  key={mensagem.id}
                  className={`flex ${mensagem.papel === "cliente" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
                      mensagem.papel === "cliente"
                        ? "bg-stone-900 text-white"
                        : "border border-stone-200 bg-stone-50 text-stone-800"
                    }`}
                  >
                    {mensagem.conteudo}
                    <span
                      className={`mt-1 block text-[10px] ${mensagem.papel === "cliente" ? "text-stone-300" : "text-stone-400"}`}
                    >
                      {mensagem.papel === "cliente" ? "Cliente" : "Chatbot"} ·{" "}
                      {formatarData(mensagem.criada_em)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
