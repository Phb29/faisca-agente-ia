"use client";

import Link from "next/link";
import { Activity, LogOut, MessageSquare } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { ErroDaApi, listarAprovacoes, listarTickets, mensagemDeErro } from "@/lib/api";
import { formatarHoje } from "@/lib/formatos";
import { useRecurso } from "@/hooks/useRecurso";
import { Aviso } from "@/components/ui/Aviso";
import { Botao, estiloDeBotao } from "@/components/ui/Botao";
import { Logotipo } from "@/components/ui/Marca";
import { NotificacaoFlutuante, type Notificacao } from "@/components/ui/Notificacao";
import { Ponto } from "@/components/ui/Pilula";
import { EditorDeMemoria } from "./EditorDeMemoria";
import { FilaDeAprovacoes } from "./FilaDeAprovacoes";
import { Indicadores } from "./Indicadores";
import { Tickets } from "./Tickets";

const SONDAGEM_MS = 5000;

type Props = {
  token: string;
  /** Sai da Central; com motivo, ele aparece na tela de login. */
  aoSair: (motivo?: string) => void;
};

export function Central({ token, aoSair }: Props) {
  const [notificacao, setNotificacao] = useState<Notificacao | null>(null);
  const sequencia = useRef(0);

  const notificar = useCallback((tom: Notificacao["tom"], texto: string) => {
    sequencia.current += 1;
    setNotificacao({ id: sequencia.current, tom, texto });
  }, []);
  const fecharNotificacao = useCallback(() => setNotificacao(null), []);

  const tokenRecusado = useCallback(
    (erro: unknown) => {
      if (erro instanceof ErroDaApi && erro.status === 401) {
        aoSair("O token foi recusado pela API. Entre de novo.");
        return true;
      }
      return false;
    },
    [aoSair],
  );

  // Falhas da sondagem ficam visíveis na faixa de aviso; só o 401 tira da Central.
  const aoFalharSondagem = useCallback((erro: unknown) => void tokenRecusado(erro), [tokenRecusado]);
  const aoFalharAcao = useCallback(
    (erro: unknown) => {
      if (!tokenRecusado(erro)) notificar("perigo", mensagemDeErro(erro));
    },
    [tokenRecusado, notificar],
  );

  const aprovacoes = useRecurso(`aprovacoes:${token}`, () => listarAprovacoes(token), {
    intervaloMs: SONDAGEM_MS,
    aoErro: aoFalharSondagem,
  });
  const tickets = useRecurso(`tickets:${token}`, () => listarTickets(token), {
    intervaloMs: SONDAGEM_MS,
    aoErro: aoFalharSondagem,
  });

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
            <Link href="/avaliacao" className={estiloDeBotao("fantasma", "sm")}>
              <Activity aria-hidden className="size-4" strokeWidth={1.8} />
              <span className="hidden sm:inline">Avaliação</span>
            </Link>
            <Link href="/" className={estiloDeBotao("fantasma", "sm")}>
              <MessageSquare aria-hidden className="size-4" strokeWidth={1.8} />
              <span className="hidden sm:inline">Abrir o chat</span>
            </Link>
            <Botao variante="fantasma" tamanho="sm" icone={LogOut} onClick={() => aoSair()}>
              Sair
            </Botao>
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
            <FilaDeAprovacoes token={token} aprovacoes={aprovacoes.dados} aoDecidir={aoDecidir} aoErro={aoFalharAcao} />
            <Tickets token={token} tickets={tickets.dados} aoErro={aoFalharAcao} />
          </div>
          <aside className="animate-surgir [animation-delay:180ms] xl:sticky xl:top-20 xl:self-start">
            <EditorDeMemoria
              token={token}
              aoSalvar={(mensagem) => notificar("sucesso", mensagem)}
              aoErro={aoFalharAcao}
            />
          </aside>
        </div>
      </main>

      <NotificacaoFlutuante notificacao={notificacao} aoFechar={fecharNotificacao} />
    </div>
  );
}
