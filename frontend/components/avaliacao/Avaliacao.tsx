"use client";

import Link from "next/link";
import { Headset, LogOut, MessageSquare } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ErroDaApi, lerAmostraEmAndamento, mensagemDeErro, type NomeDoEval } from "@/lib/api";
import { ABAS, abaValida, TEXTOS } from "@/lib/avaliacao";
import { useRecurso } from "@/hooks/useRecurso";
import { Botao, estiloDeBotao } from "@/components/ui/Botao";
import { Logotipo } from "@/components/ui/Marca";
import { NotificacaoFlutuante, type Notificacao } from "@/components/ui/Notificacao";
import { Ponto } from "@/components/ui/Pilula";
import { Segmentos } from "@/components/ui/Segmentos";
import { PainelDoEval } from "./PainelDoEval";

const SONDAGEM_MS = 5000;

type Props = {
  token: string;
  /** Sai da avaliação; com motivo, ele aparece na tela de login. */
  aoSair: (motivo?: string) => void;
};

export function Avaliacao({ token, aoSair }: Props) {
  const router = useRouter();
  const aba = abaValida(useSearchParams().get("aba"));
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
  const aoFalhar = useCallback(
    (erro: unknown) => {
      if (!tokenRecusado(erro)) notificar("perigo", mensagemDeErro(erro));
    },
    [tokenRecusado, notificar],
  );

  const amostra = useRecurso(`amostra:${token}`, () => lerAmostraEmAndamento(token), {
    intervaloMs: SONDAGEM_MS,
    aoErro: (erro) => void tokenRecusado(erro),
  });

  const trocarAba = useCallback(
    (nova: NomeDoEval) => router.replace(`/avaliacao?aba=${nova}`, { scroll: false }),
    [router],
  );

  // 1, 2 e 3 trocam de aba, para o apresentador não precisar mirar o mouse no telão.
  useEffect(() => {
    const aoTeclar = (evento: KeyboardEvent) => {
      if (evento.metaKey || evento.ctrlKey || evento.altKey) return;
      const alvo = evento.target as HTMLElement | null;
      if (alvo && (alvo.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(alvo.tagName))) return;
      // Com a gaveta de detalhe aberta, o foco costuma estar no body: não trocar de aba atrás dela.
      if (document.querySelector('[aria-modal="true"]')) return;
      const indice = ["1", "2", "3"].indexOf(evento.key);
      if (indice >= 0) trocarAba(ABAS[indice]);
    };
    document.addEventListener("keydown", aoTeclar);
    return () => document.removeEventListener("keydown", aoTeclar);
  }, [trocarAba]);

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-line bg-canvas/85 backdrop-blur-md">
        <div className="mx-auto flex min-h-14 max-w-[1320px] flex-wrap items-center gap-x-4 gap-y-2 px-5 py-2 2xl:max-w-[1600px]">
          <Logotipo />
          <span aria-hidden className="hidden h-5 w-px bg-line sm:block" />
          <Segmentos
            rotulo="Eval mostrado"
            valor={aba}
            aoMudar={trocarAba}
            opcoes={ABAS.map((nome, indice) => ({
              valor: nome,
              rotulo: (
                <>
                  <span className="font-mono text-[10px] opacity-60">{indice + 1}</span>
                  {TEXTOS[nome].rotulo}
                </>
              ),
            }))}
          />
          <div className="ml-auto flex items-center gap-3">
            <span className="sobretitulo hidden items-center gap-2 md:flex" title="Atualiza a cada 5 segundos">
              <Ponto tom={amostra.erro ? "perigo" : "volt"} pulsando={!amostra.erro} />
              {amostra.erro ? "Sem conexão" : "Ao vivo"}
            </span>
            <div className="flex items-center gap-1.5">
              <Link href="/atendente" aria-label="Central do Atendente" className={estiloDeBotao("fantasma", "sm")}>
                <Headset aria-hidden className="size-4" strokeWidth={1.8} />
                <span className="hidden md:inline">Central do Atendente</span>
              </Link>
              <Link href="/" aria-label="Abrir o chat" className={estiloDeBotao("fantasma", "sm")}>
                <MessageSquare aria-hidden className="size-4" strokeWidth={1.8} />
                <span className="hidden md:inline">Abrir o chat</span>
              </Link>
              <Botao variante="fantasma" tamanho="sm" icone={LogOut} aria-label="Sair" onClick={() => aoSair()}>
                <span className="hidden sm:inline">Sair</span>
              </Botao>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1320px] px-5 pb-20 2xl:max-w-[1600px]">
        <PainelDoEval
          key={aba}
          nome={aba}
          token={token}
          // Com a sondagem falhando, o último valor fica velho: melhor não mostrar o botão
          // "rodando" de um eval que pode já ter terminado.
          amostraGlobal={amostra.erro ? null : amostra.dados}
          recarregarAmostraGlobal={amostra.recarregar}
          aoIrPara={trocarAba}
          aoFalhar={aoFalhar}
        />
      </main>

      <NotificacaoFlutuante notificacao={notificacao} aoFechar={fecharNotificacao} />
    </div>
  );
}
