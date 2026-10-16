"use client";

import { Menu, PanelRight, PanelRightClose } from "lucide-react";
import type { StatusDaConversa } from "@/lib/api";
import type { Tom } from "@/lib/rotulos";
import { statusDaConversa } from "@/lib/rotulos";
import type { Conexao } from "@/lib/sse";
import { BotaoSair } from "@/components/acesso/BotaoSair";
import { BotaoDeIcone } from "@/components/ui/Botao";
import { PilulaDe, Ponto } from "@/components/ui/Pilula";

type Props = {
  titulo: string;
  status: StatusDaConversa | null;
  conexao: Conexao | null;
  painelAberto: boolean;
  aoAbrirMenu: () => void;
  aoAlternarPainel: () => void;
};

const CONEXAO: Record<Conexao, { rotulo: string; tom: Tom; pulsando: boolean }> = {
  aberta: { rotulo: "Ao vivo", tom: "volt", pulsando: true },
  conectando: { rotulo: "Conectando", tom: "neutro", pulsando: true },
  reconectando: { rotulo: "Reconectando", tom: "alerta", pulsando: true },
  fechada: { rotulo: "Desconectado", tom: "perigo", pulsando: false },
};

export function Cabecalho({ titulo, status, conexao, painelAberto, aoAbrirMenu, aoAlternarPainel }: Props) {
  const estado = conexao ? CONEXAO[conexao] : null;
  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b border-line px-3 sm:px-5">
      <BotaoDeIcone icone={Menu} rotulo="Abrir Conversas" className="lg:hidden" onClick={aoAbrirMenu} />
      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        <h1 className="truncate text-[14.5px] font-medium">{titulo}</h1>
        {status && <PilulaDe rotulo={statusDaConversa(status)} className="hidden sm:inline-flex" />}
      </div>
      {estado && (
        <span className="sobretitulo mr-1 flex items-center gap-2" aria-live="polite">
          <Ponto tom={estado.tom} pulsando={estado.pulsando} />
          <span className="hidden sm:inline">{estado.rotulo}</span>
        </span>
      )}
      <BotaoDeIcone
        icone={painelAberto ? PanelRightClose : PanelRight}
        rotulo={painelAberto ? "Fechar painel de contexto" : "Abrir painel de contexto"}
        aria-expanded={painelAberto}
        onClick={aoAlternarPainel}
      />
      {/* Sair encerra o login; trocar de Cliente (na barra de Conversas) só volta à escolha. */}
      <span aria-hidden className="mx-0.5 h-5 w-px bg-line" />
      <BotaoSair />
    </header>
  );
}
