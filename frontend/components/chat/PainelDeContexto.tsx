"use client";

import { Activity, Flag, Package, X } from "lucide-react";
import type { ReactNode } from "react";
import type { Desfecho, Pedido } from "@/lib/api";
import { cx } from "@/lib/cx";
import { formatarDiaDoCalendario, formatarHora, formatarReais, primeiroNome } from "@/lib/formatos";
import { acao, linha, noDoGrafo, statusDoPedido } from "@/lib/rotulos";
import type { Passo } from "@/hooks/useConversa";
import { iconeDaAcao, iconeDoNo } from "@/components/icones";
import { BotaoDeIcone } from "@/components/ui/Botao";
import { Carregando } from "@/components/ui/Carregando";
import { Gaveta } from "@/components/ui/Gaveta";
import { Pilula, PilulaDe, Ponto } from "@/components/ui/Pilula";
import { Segmentos } from "@/components/ui/Segmentos";
import { Esqueleto, Vazio } from "@/components/ui/Vazio";

export type Aba = "pedidos" | "bastidores";

export type EstadoDoPainel = {
  /** Coluna fixa em telas largas. */
  aberto: boolean;
  /** Gaveta sobreposta em telas estreitas. */
  naGaveta: boolean;
  aba: Aba;
  definirAba: (aba: Aba) => void;
  alternar: () => void;
  /** Fecha a coluna e a gaveta. */
  fechar: () => void;
  /** Fecha só a gaveta (a coluna das telas largas continua como está). */
  fecharGaveta: () => void;
};

type Props = {
  painel: EstadoDoPainel;
  nomeDoCliente: string;
  pedidos: Pedido[] | null;
  passos: Passo[];
  desfecho: Desfecho | null;
  trabalhando: boolean;
  aoUsarPedido: (pedido: Pedido) => void;
};

/** Contexto do atendimento: os Pedidos do Cliente e os bastidores do grafo, ao vivo. */
export function PainelDeContexto({ painel, ...conteudo }: Props) {
  const corpo = <Conteudo painel={painel} {...conteudo} />;
  return (
    <>
      {painel.aberto && (
        <aside
          aria-label="Contexto do atendimento"
          className="hidden w-[340px] shrink-0 flex-col border-l border-line bg-surface-2 xl:flex"
        >
          {corpo}
        </aside>
      )}
      <Gaveta
        aberta={painel.naGaveta}
        aoFechar={painel.fecharGaveta}
        rotulo="Contexto do atendimento"
        largura="max-w-[360px]"
        className="bg-surface-2 xl:hidden"
      >
        {corpo}
      </Gaveta>
    </>
  );
}

function Conteudo({ painel, nomeDoCliente, pedidos, passos, desfecho, trabalhando, aoUsarPedido }: Props) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex h-14 shrink-0 items-center gap-2 border-b border-line px-3">
        <Segmentos
          rotulo="Contexto do atendimento"
          className="flex-1"
          valor={painel.aba}
          aoMudar={painel.definirAba}
          opcoes={[
            { valor: "pedidos", rotulo: "Pedidos" },
            {
              valor: "bastidores",
              rotulo: (
                <>
                  Bastidores
                  {trabalhando && <Ponto tom="volt" pulsando />}
                </>
              ),
            },
          ]}
        />
        <BotaoDeIcone icone={X} rotulo="Fechar painel de contexto" tamanho="sm" onClick={painel.fechar} />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4" role="tabpanel">
        {painel.aba === "pedidos" ? (
          <ListaDePedidos nomeDoCliente={nomeDoCliente} pedidos={pedidos} aoUsar={aoUsarPedido} />
        ) : (
          <Bastidores passos={passos} desfecho={desfecho} trabalhando={trabalhando} />
        )}
      </div>
    </div>
  );
}

function Titulo({ children, contagem }: { children: ReactNode; contagem?: number }) {
  return (
    <div className="mb-3 flex items-baseline justify-between">
      <h2 className="text-[13px] font-medium text-ink">{children}</h2>
      {contagem !== undefined && <span className="font-mono text-[11px] text-muted">{contagem}</span>}
    </div>
  );
}

function ListaDePedidos({
  nomeDoCliente,
  pedidos,
  aoUsar,
}: {
  nomeDoCliente: string;
  pedidos: Pedido[] | null;
  aoUsar: (pedido: Pedido) => void;
}) {
  if (pedidos === null) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <Esqueleto key={i} className="h-[118px] rounded-xl" />
        ))}
      </div>
    );
  }
  if (pedidos.length === 0) {
    return (
      <Vazio icone={Package} titulo="Nenhum Pedido">
        Este Cliente ainda não comprou na Loja. Pergunte sobre políticas de troca, frete ou garantia.
      </Vazio>
    );
  }
  return (
    <section>
      <Titulo contagem={pedidos.length}>Pedidos de {primeiroNome(nomeDoCliente)}</Titulo>
      <ul className="space-y-2">
        {pedidos.map((pedido, indice) => (
          <li key={pedido.id} className="animate-surgir" style={{ animationDelay: `${indice * 40}ms` }}>
            <button
              type="button"
              onClick={() => aoUsar(pedido)}
              title="Perguntar sobre este Pedido"
              className="w-full rounded-xl bg-surface p-3.5 text-left shadow-suave ring-1 ring-line transition ring-inset hover:shadow-elevada hover:ring-line-strong"
            >
              <span className="flex items-start justify-between gap-3">
                <span className="text-[13.5px] leading-snug font-medium text-ink">{pedido.produto}</span>
                <span className="font-mono text-[12.5px] text-ink tabular-nums">{formatarReais(pedido.valor)}</span>
              </span>
              <span className="mt-2.5 flex items-center justify-between gap-2">
                <PilulaDe rotulo={statusDoPedido(pedido.status)} />
                <span className="text-[11.5px] text-muted">{linha(pedido.linha)}</span>
              </span>
              <span className="mt-3 flex items-center justify-between border-t border-line pt-2.5 font-mono text-[10.5px] text-muted">
                <span>{pedido.id}</span>
                <span>{formatarDiaDoCalendario(pedido.data)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      <p className="mt-3 px-1 text-[11.5px] leading-relaxed text-muted">
        Clique num Pedido para perguntar sobre ele.
      </p>
    </section>
  );
}

function resumoDosArgs(args: Record<string, unknown>): string | null {
  const partes = Object.values(args).filter((v): v is string | number => typeof v === "string" || typeof v === "number");
  return partes.length ? partes.join(" · ") : null;
}

function Bastidores({ passos, desfecho, trabalhando }: { passos: Passo[]; desfecho: Desfecho | null; trabalhando: boolean }) {
  if (passos.length === 0 && !trabalhando) {
    return (
      <Vazio icone={Activity} titulo="Nenhum turno ainda">
        Envie uma mensagem para ver o grafo trabalhar: guardrails, roteador, Ações e memória.
      </Vazio>
    );
  }
  return (
    <section>
      <Titulo>O caminho da última mensagem</Titulo>
      <ol className="relative">
        {passos.map((passo, indice) => (
          <ItemDoPasso key={passo.id} passo={passo} ultimo={indice === passos.length - 1 && !trabalhando} />
        ))}
        {trabalhando && (
          <li className="flex items-center gap-3 pb-1 text-[12.5px] text-muted">
            <span className="flex size-7 items-center justify-center">
              <Carregando className="size-3.5" rotulo="Processando" />
            </span>
            <span className="texto-brilhante">Processando</span>
          </li>
        )}
      </ol>
      {desfecho && (
        <div className="mt-3 flex items-center justify-between rounded-xl bg-surface px-3.5 py-3 shadow-suave ring-1 ring-line">
          <span className="flex items-center gap-2 text-[12.5px] text-ink-2">
            <Flag aria-hidden className="size-3.5 text-muted" strokeWidth={1.8} /> Desfecho
          </span>
          <Pilula tom={desfecho === "Resolvida" ? "sucesso" : "info"} ponto>
            {desfecho}
          </Pilula>
        </div>
      )}
    </section>
  );
}

function ItemDoPasso({ passo, ultimo }: { passo: Passo; ultimo: boolean }) {
  const ehAcao = passo.tipo === "acao";
  const Icone = ehAcao ? iconeDaAcao(passo.nome) : iconeDoNo(passo.no);
  const rotulo = ehAcao ? acao(passo.nome).rotulo : noDoGrafo(passo.no).rotulo;
  const detalhe = ehAcao ? resumoDosArgs(passo.args) : passo.detalhe;
  const alerta = !ehAcao && passo.alerta;

  return (
    <li className="relative flex animate-surgir gap-3 pb-4">
      {!ultimo && <span aria-hidden className="absolute top-8 bottom-1 left-[13.5px] w-px bg-line" />}
      <span
        className={cx(
          "relative flex size-7 shrink-0 items-center justify-center rounded-lg ring-1 ring-inset",
          alerta
            ? "bg-alerta-soft text-alerta ring-alerta/25"
            : ehAcao
              ? "bg-noite text-volt ring-noite-line"
              : "bg-surface text-ink-2 ring-line",
        )}
      >
        <Icone aria-hidden className="size-3.5" strokeWidth={1.8} />
      </span>
      <div className="min-w-0 flex-1 pt-[3px]">
        <div className="flex items-baseline justify-between gap-2">
          <p className={cx("text-[13px] font-medium", alerta ? "text-alerta" : "text-ink")}>
            {ehAcao && <span className="sobretitulo mr-1.5 text-[9.5px]">Ação</span>}
            {rotulo}
          </p>
          <time dateTime={passo.em} className="shrink-0 font-mono text-[10px] text-muted">
            {formatarHora(passo.em, { segundos: true })}
          </time>
        </div>
        {detalhe && <p className="mt-0.5 font-mono text-[11.5px] leading-relaxed break-words text-muted">{detalhe}</p>}
      </div>
    </li>
  );
}
