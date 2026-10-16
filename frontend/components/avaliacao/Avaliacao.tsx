"use client";

import Link from "next/link";
import { Headset, MessageSquare } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { lerAmostraEmAndamento, mensagemDeErro, sessaoRecusada } from "@/lib/api";
import { ABAS, abaValida, rotuloDaAba, type Aba } from "@/lib/avaliacao";
import { useRecurso } from "@/hooks/useRecurso";
import { BotaoSair } from "@/components/acesso/BotaoSair";
import { estiloDeBotao } from "@/components/ui/Botao";
import { Logotipo } from "@/components/ui/Marca";
import { NotificacaoFlutuante, type Notificacao } from "@/components/ui/Notificacao";
import { Ponto } from "@/components/ui/Pilula";
import { Segmentos } from "@/components/ui/Segmentos";
import { PainelDeDados } from "./PainelDeDados";
import { PainelDoEval } from "./PainelDoEval";

const SONDAGEM_MS = 5000;

export function Avaliacao() {
  const router = useRouter();
  const aba = abaValida(useSearchParams().get("aba"));
  const [notificacao, setNotificacao] = useState<Notificacao | null>(null);
  const sequencia = useRef(0);

  const notificar = useCallback((tom: Notificacao["tom"], texto: string) => {
    sequencia.current += 1;
    setNotificacao({ id: sequencia.current, tom, texto });
  }, []);
  const fecharNotificacao = useCallback(() => setNotificacao(null), []);

  // A sessão recusada (401) já leva à tela de entrada pelo `requisitar`: não vira notificação.
  const aoFalhar = useCallback(
    (erro: unknown) => {
      if (!sessaoRecusada(erro)) notificar("perigo", mensagemDeErro(erro));
    },
    [notificar],
  );

  const amostra = useRecurso("amostra", lerAmostraEmAndamento, { intervaloMs: SONDAGEM_MS });

  const trocarAba = useCallback(
    (nova: Aba) => router.replace(`/avaliacao?aba=${nova}`, { scroll: false }),
    [router],
  );

  // 1 a 4 trocam de aba, para o apresentador não precisar mirar o mouse no telão.
  useEffect(() => {
    const aoTeclar = (evento: KeyboardEvent) => {
      if (evento.metaKey || evento.ctrlKey || evento.altKey) return;
      const alvo = evento.target as HTMLElement | null;
      if (alvo && (alvo.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(alvo.tagName))) return;
      // Com a gaveta de detalhe aberta, o foco costuma estar no body: não trocar de aba atrás dela.
      if (document.querySelector('[aria-modal="true"]')) return;
      const indice = ["1", "2", "3", "4"].indexOf(evento.key);
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
                  {rotuloDaAba(nome)}
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
              <BotaoSair />
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1320px] px-5 pb-20 2xl:max-w-[1600px]">
        {aba === "dados" ? (
          <PainelDeDados aoFalhar={aoFalhar} />
        ) : (
          <PainelDoEval
            key={aba}
            nome={aba}
            // Com a sondagem falhando, o último valor fica velho: melhor não mostrar o botão
            // "rodando" de um eval que pode já ter terminado.
            amostraGlobal={amostra.erro ? null : amostra.dados}
            recarregarAmostraGlobal={amostra.recarregar}
            aoIrPara={trocarAba}
            aoFalhar={aoFalhar}
          />
        )}
      </main>

      <NotificacaoFlutuante notificacao={notificacao} aoFechar={fecharNotificacao} />
    </div>
  );
}
