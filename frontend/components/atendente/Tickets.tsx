"use client";

import { ChevronRight, LifeBuoy, X } from "lucide-react";
import { useState } from "react";
import { lerConversaDoTicket, type ConversaDoTicket, type Prioridade, type Ticket } from "@/lib/api";
import { cx } from "@/lib/cx";
import { formatarMomento, formatarRelativo } from "@/lib/formatos";
import { categoria, prioridade as rotuloDePrioridade } from "@/lib/rotulos";
import { useRecurso } from "@/hooks/useRecurso";
import { MensagemDoAssistente, MensagemDoCliente } from "@/components/chat/Mensagens";
import { BotaoDeIcone } from "@/components/ui/Botao";
import { CabecalhoDeSecao } from "@/components/ui/CabecalhoDeSecao";
import { Gaveta } from "@/components/ui/Gaveta";
import { Pilula } from "@/components/ui/Pilula";
import { Segmentos } from "@/components/ui/Segmentos";
import { TOM_SOLIDO } from "@/components/ui/tons";
import { Esqueleto, Vazio } from "@/components/ui/Vazio";

type Filtro = "todos" | Prioridade;

type Props = {
  tickets: Ticket[] | null;
  aoErro: (erro: unknown) => void;
};

export function Tickets({ tickets, aoErro }: Props) {
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [abertoId, setAbertoId] = useState<string | null>(null);
  const visiveis = (tickets ?? []).filter((t) => filtro === "todos" || t.prioridade === filtro);

  return (
    <section aria-labelledby="titulo-tickets">
      <CabecalhoDeSecao
        id="titulo-tickets"
        titulo="Tickets"
        descricao="Conversas que o chatbot escalou, com resumo, categoria e prioridade escritos pelo trabalhador."
        contagem={tickets?.length}
      >
        <Segmentos
          rotulo="Filtrar por prioridade"
          valor={filtro}
          aoMudar={setFiltro}
          opcoes={[
            { valor: "todos", rotulo: "Todos" },
            { valor: "alta", rotulo: "Alta" },
            { valor: "media", rotulo: "Média" },
            { valor: "baixa", rotulo: "Baixa" },
          ]}
        />
      </CabecalhoDeSecao>

      <div className="overflow-hidden rounded-2xl bg-surface shadow-suave ring-1 ring-line">
        {tickets === null ? (
          <div className="divide-y divide-line">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-4 px-5 py-4">
                <Esqueleto className="h-3 w-12" />
                <Esqueleto className="h-3 flex-1" />
                <Esqueleto className="h-3 w-16" />
              </div>
            ))}
          </div>
        ) : visiveis.length === 0 ? (
          <Vazio icone={LifeBuoy} titulo={filtro === "todos" ? "Nenhum Ticket aberto" : "Nenhum Ticket com essa prioridade"}>
            Quando o chatbot não conseguir resolver, a Conversa chega aqui com um resumo.
          </Vazio>
        ) : (
          <table className="w-full table-fixed text-left">
            <thead className="border-b border-line bg-surface-2">
              <tr className="sobretitulo">
                <th scope="col" className="w-[118px] px-5 py-2.5 font-medium">Prioridade</th>
                <th scope="col" className="px-3 py-2.5 font-medium">Resumo</th>
                <th scope="col" className="hidden w-[120px] px-3 py-2.5 font-medium md:table-cell">Categoria</th>
                <th scope="col" className="hidden w-[118px] px-3 py-2.5 font-medium lg:table-cell">Cliente</th>
                <th scope="col" className="hidden w-[92px] px-3 py-2.5 font-medium sm:table-cell">Aberto</th>
                <th scope="col" className="w-12 px-3 py-2.5">
                  <span className="sr-only">Abrir</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {visiveis.map((ticket) => (
                <LinhaDoTicket key={ticket.id} ticket={ticket} aoAbrir={() => setAbertoId(ticket.id)} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      <ConversaDoTicketNaGaveta ticketId={abertoId} aoFechar={() => setAbertoId(null)} aoErro={aoErro} />
    </section>
  );
}

function IndicadorDePrioridade({ valor }: { valor: string }) {
  const rotulo = rotuloDePrioridade(valor);
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden className="flex h-3 items-end gap-[2px]">
        {[1, 2, 3].map((nivel) => (
          <span
            key={nivel}
            className={cx("w-[3px] rounded-full", nivel <= rotulo.nivel ? TOM_SOLIDO[rotulo.tom] : "bg-line-strong")}
            style={{ height: `${4 + nivel * 2.5}px` }}
          />
        ))}
      </span>
      <span className="text-[12.5px] text-ink-2">{rotulo.rotulo}</span>
    </span>
  );
}

function LinhaDoTicket({ ticket, aoAbrir }: { ticket: Ticket; aoAbrir: () => void }) {
  return (
    <tr onClick={aoAbrir} className="group cursor-pointer align-top transition-colors hover:bg-surface-2">
      <td className="px-5 py-4">
        <IndicadorDePrioridade valor={ticket.prioridade} />
      </td>
      <td className="px-3 py-4">
        <button
          type="button"
          onClick={(evento) => {
            evento.stopPropagation();
            aoAbrir();
          }}
          className="line-clamp-2 text-left text-[13.5px] leading-relaxed text-ink"
        >
          {ticket.resumo}
        </button>
      </td>
      <td className="hidden px-3 py-4 md:table-cell">
        <Pilula>{categoria(ticket.categoria)}</Pilula>
      </td>
      <td className="hidden truncate px-3 py-4 font-mono text-[11.5px] text-muted lg:table-cell">{ticket.cliente_id}</td>
      <td className="hidden px-3 py-4 font-mono text-[11.5px] whitespace-nowrap text-muted sm:table-cell">
        <time dateTime={ticket.criado_em}>{formatarRelativo(ticket.criado_em)}</time>
      </td>
      <td className="px-3 py-4 text-right">
        <ChevronRight aria-hidden className="ml-auto size-4 text-muted transition group-hover:translate-x-0.5 group-hover:text-ink" />
      </td>
    </tr>
  );
}

type PropsDaGaveta = {
  ticketId: string | null;
  aoFechar: () => void;
  aoErro: (erro: unknown) => void;
};

function ConversaDoTicketNaGaveta({ ticketId, aoFechar, aoErro }: PropsDaGaveta) {
  const conversa = useRecurso<ConversaDoTicket>(
    ticketId ? `ticket:${ticketId}` : null,
    () => lerConversaDoTicket(ticketId ?? ""),
    { aoErro },
  );

  return (
    <Gaveta aberta={ticketId !== null} aoFechar={aoFechar} rotulo="Conversa do Ticket">
      <header className="shrink-0 border-b border-line px-6 py-5">
        <div className="flex items-start justify-between gap-4">
          <p className="sobretitulo">
            Ticket {ticketId && <span className="normal-case">· {ticketId.slice(0, 8)}</span>}
          </p>
          <BotaoDeIcone icone={X} rotulo="Fechar" tamanho="sm" className="-mt-1.5 -mr-2" onClick={aoFechar} />
        </div>
        {conversa.dados ? (
          <>
            <p className="mt-3 text-[15px] leading-relaxed text-ink">{conversa.dados.ticket.resumo}</p>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Pilula tom={rotuloDePrioridade(conversa.dados.ticket.prioridade).tom} ponto>
                Prioridade {rotuloDePrioridade(conversa.dados.ticket.prioridade).rotulo.toLowerCase()}
              </Pilula>
              <Pilula>{categoria(conversa.dados.ticket.categoria)}</Pilula>
              <span className="font-mono text-[11px] text-muted">
                {conversa.dados.ticket.cliente_id} · {formatarMomento(conversa.dados.ticket.criado_em)}
              </span>
            </div>
          </>
        ) : (
          <div className="mt-4 space-y-2.5">
            <Esqueleto className="h-3.5 w-full" />
            <Esqueleto className="h-3.5 w-2/3" />
          </div>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto bg-surface px-6 py-6">
        {conversa.dados ? (
          conversa.dados.mensagens.length === 0 ? (
            <p className="text-[13px] text-muted">Esta Conversa não tem mensagens gravadas.</p>
          ) : (
            <ol className="flex flex-col gap-6" aria-label="Mensagens da Conversa">
              {conversa.dados.mensagens.map((mensagem) =>
                mensagem.papel === "cliente" ? (
                  <MensagemDoCliente key={mensagem.id} mensagem={mensagem} />
                ) : (
                  <MensagemDoAssistente key={mensagem.id} mensagem={mensagem} />
                ),
              )}
            </ol>
          )
        ) : (
          <div className="space-y-6">
            <Esqueleto className="ml-auto h-10 w-2/3 rounded-[20px]" />
            <Esqueleto className="h-16 w-5/6" />
          </div>
        )}
      </div>
    </Gaveta>
  );
}
