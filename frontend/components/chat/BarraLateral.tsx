"use client";

import Link from "next/link";
import { Headset, LogOut, MessageSquare, Plus } from "lucide-react";
import type { Conversa } from "@/lib/api";
import { cx } from "@/lib/cx";
import { formatarRelativo, periodoDe, type Periodo } from "@/lib/formatos";
import { statusDaConversa } from "@/lib/rotulos";
import { Avatar } from "@/components/ui/Avatar";
import { Botao, BotaoDeIcone } from "@/components/ui/Botao";
import { Logotipo } from "@/components/ui/Marca";
import { Ponto } from "@/components/ui/Pilula";
import { Esqueleto, Vazio } from "@/components/ui/Vazio";
import type { ClienteEscolhido } from "./TelaDeEntrada";

type Props = {
  cliente: ClienteEscolhido;
  conversas: Conversa[] | null;
  ativaId: string | null;
  aoSelecionar: (id: string) => void;
  aoNova: () => void;
  aoSair: () => void;
};

const PERIODOS: Periodo[] = ["Hoje", "Últimos 7 dias", "Anteriores"];

function agrupar(conversas: Conversa[]) {
  const agora = new Date();
  return PERIODOS.map((periodo) => ({
    periodo,
    conversas: conversas.filter((c) => periodoDe(c.atualizada_em, agora) === periodo),
  })).filter((grupo) => grupo.conversas.length > 0);
}

export function BarraLateral({ cliente, conversas, ativaId, aoSelecionar, aoNova, aoSair }: Props) {
  return (
    <nav aria-label="Conversas" className="flex h-full w-full flex-col bg-canvas">
      <div className="flex h-14 shrink-0 items-center px-4">
        <Logotipo subtitulo="Suporte" />
      </div>

      <div className="px-3 pt-1 pb-2">
        <Botao variante="secundario" icone={Plus} className="w-full justify-start" onClick={aoNova}>
          Nova conversa
        </Botao>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
        {conversas === null ? (
          <div className="space-y-3 px-3 pt-5" aria-label="Carregando Conversas">
            {[72, 56, 64, 48].map((largura) => (
              <Esqueleto key={largura} className="h-4" style={{ width: `${largura}%` }} />
            ))}
          </div>
        ) : conversas.length === 0 ? (
          <Vazio icone={MessageSquare} titulo="Nenhuma Conversa ainda" className="py-12">
            Suas Conversas com o suporte aparecem aqui.
          </Vazio>
        ) : (
          agrupar(conversas).map((grupo) => (
            <section key={grupo.periodo} className="pt-4">
              <h2 className="sobretitulo px-3 pb-1.5">{grupo.periodo}</h2>
              <ul className="space-y-px">
                {grupo.conversas.map((conversa) => (
                  <ItemDeConversa
                    key={conversa.id}
                    conversa={conversa}
                    ativa={conversa.id === ativaId}
                    aoSelecionar={aoSelecionar}
                  />
                ))}
              </ul>
            </section>
          ))
        )}
      </div>

      <div className="shrink-0 space-y-1 border-t border-line p-3">
        <Link
          href="/atendente"
          className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-ink-2 transition-colors hover:bg-canvas-2 hover:text-ink"
        >
          <Headset aria-hidden className="size-4 text-muted" strokeWidth={1.7} />
          Central do Atendente
        </Link>
        <div className="flex items-center gap-3 rounded-xl bg-surface p-2.5 shadow-suave ring-1 ring-line">
          <Avatar nome={cliente.nome} semente={cliente.id} tamanho="sm" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-medium">{cliente.nome}</p>
            <p className="truncate font-mono text-[10.5px] text-muted">{cliente.id}</p>
          </div>
          <BotaoDeIcone icone={LogOut} rotulo="Trocar de Cliente" tamanho="sm" onClick={aoSair} />
        </div>
      </div>
    </nav>
  );
}

function ItemDeConversa({
  conversa,
  ativa,
  aoSelecionar,
}: {
  conversa: Conversa;
  ativa: boolean;
  aoSelecionar: (id: string) => void;
}) {
  const status = statusDaConversa(conversa.status);
  return (
    <li>
      <button
        type="button"
        onClick={() => aoSelecionar(conversa.id)}
        aria-current={ativa ? "page" : undefined}
        title={status.rotulo}
        className={cx(
          "relative flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left transition-colors",
          ativa ? "bg-surface shadow-suave ring-1 ring-line" : "hover:bg-canvas-2",
        )}
      >
        {ativa && <span aria-hidden className="absolute inset-y-2 -left-2 w-[3px] rounded-r-full bg-volt ring-1 ring-volt-forte" />}
        <Ponto tom={status.tom} />
        <span className={cx("min-w-0 flex-1 truncate text-[13.5px]", ativa ? "text-ink" : "text-ink-2")}>
          {conversa.titulo || "Nova conversa"}
        </span>
        <time dateTime={conversa.atualizada_em} className="shrink-0 font-mono text-[10.5px] text-muted">
          {formatarRelativo(conversa.atualizada_em)}
        </time>
      </button>
    </li>
  );
}
