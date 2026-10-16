"use client";

import Link from "next/link";
import { Activity, MessageSquare } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { listarAprovacoes, listarTickets, mensagemDeErro, sessaoRecusada } from "@/lib/api";
import { formatarHoje } from "@/lib/formatos";
import { useRecurso } from "@/hooks/useRecurso";
import { BotaoSair } from "@/components/acesso/BotaoSair";
import { Aviso } from "@/components/ui/Aviso";
import { estiloDeBotao } from "@/components/ui/Botao";
import { Logotipo } from "@/components/ui/Marca";
import { NotificacaoFlutuante, type Notificacao } from "@/components/ui/Notificacao";
import { Ponto } from "@/components/ui/Pilula";
import { EditorDeMemoria } from "./EditorDeMemoria";
import { FilaDeAprovacoes } from "./FilaDeAprovacoes";
import { Indicadores } from "./Indicadores";
import { Tickets } from "./Tickets";

const SONDAGEM_MS = 5000;

export function Central() {
  const [notificacao, setNotificacao] = useState<Notificacao | null>(null);
  const sequencia = useRef(0);

  const notificar = useCallback((tom: Notificacao["tom"], texto: string) => {
    sequencia.current += 1;
    setNotificacao({ id: sequencia.current, tom, texto });
  }, []);
  const fecharNotificacao = useCallback(() => setNotificacao(null), []);

  // Falhas da sondagem ficam visíveis na faixa de aviso. A sessão recusada (401) já leva à
  // tela de entrada pelo `requisitar`, então não vira notificação.
  const aoFalharAcao = useCallback(
    (erro: unknown) => {
      if (!sessaoRecusada(erro)) notificar("perigo", mensagemDeErro(erro));
    },
    [notificar],
  );

  const aprovacoes = useRecurso("aprovacoes", listarAprovacoes, { intervaloMs: SONDAGEM_MS });
  const tickets = useRecurso("tickets", listarTickets, { intervaloMs: SONDAGEM_MS });

  const recarregarAprovacoes = aprovacoes.recarregar;
  const aoDecidir = useCallback(
    (mensagem: string) => {
      notificar("sucesso", mensagem);
      void recarregarAprovacoes();
    },
    [notificar, recarregarAprovacoes],
  );

  const erroDaSondagem = aprovacoes.erro ?? tickets.erro;

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-line bg-canvas/85 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-[1320px] items-center gap-4 px-5">
          <Logotipo />
          <span aria-hidden className="hidden h-5 w-px bg-line sm:block" />
          <span className="hidden text-[13.5px] font-medium text-ink-2 sm:block">Central do Atendente</span>
          <div className="ml-auto flex items-center gap-1.5">
            <span className="sobretitulo mr-2 hidden items-center gap-2 md:flex" title="Atualiza a cada 5 segundos">
              <Ponto tom={erroDaSondagem ? "perigo" : "volt"} pulsando={!erroDaSondagem} />
              {erroDaSondagem ? "Sem conexão" : "Ao vivo"}
            </span>
            <Link href="/avaliacao" aria-label="Avaliação" className={estiloDeBotao("fantasma", "sm")}>
              <Activity aria-hidden className="size-4" strokeWidth={1.8} />
              <span className="hidden sm:inline">Avaliação</span>
            </Link>
            <Link href="/" aria-label="Abrir o chat" className={estiloDeBotao("fantasma", "sm")}>
              <MessageSquare aria-hidden className="size-4" strokeWidth={1.8} />
              <span className="hidden sm:inline">Abrir o chat</span>
            </Link>
            <BotaoSair />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1320px] px-5 pb-20">
        <div className="animate-surgir pt-10 pb-8">
          <p className="sobretitulo">{formatarHoje()}</p>
          <h1 className="mt-2 font-display text-[clamp(30px,3.4vw,40px)] leading-[1.05] font-semibold tracking-[-0.035em]">
            Central do Atendente
          </h1>
        </div>

        {erroDaSondagem !== null && (
          <Aviso className="mb-6">Não foi possível atualizar agora. {mensagemDeErro(erroDaSondagem)}</Aviso>
        )}

        <div className="animate-surgir [animation-delay:60ms]">
          <Indicadores aprovacoes={aprovacoes.dados} tickets={tickets.dados} />
        </div>

        <div className="mt-10 grid gap-10 xl:grid-cols-[minmax(0,1fr)_380px]">
          <div className="min-w-0 animate-surgir space-y-12 [animation-delay:120ms]">
            <FilaDeAprovacoes aprovacoes={aprovacoes.dados} aoDecidir={aoDecidir} aoErro={aoFalharAcao} />
            <Tickets tickets={tickets.dados} aoErro={aoFalharAcao} />
          </div>
          <aside className="animate-surgir [animation-delay:180ms] xl:sticky xl:top-20 xl:self-start">
            <EditorDeMemoria aoSalvar={(mensagem) => notificar("sucesso", mensagem)} aoErro={aoFalharAcao} />
          </aside>
        </div>
      </main>

      <NotificacaoFlutuante notificacao={notificacao} aoFechar={fecharNotificacao} />
    </div>
  );
}
