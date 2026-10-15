"use client";

import { useLayoutEffect, useRef } from "react";
import type { StatusDaConversa } from "@/lib/api";
import type { EventoApprovalRequired } from "@/lib/sse";
import type { EstadoDaConversa } from "@/hooks/useConversa";
import { Esqueleto } from "@/components/ui/Vazio";
import {
  AcaoEmAndamento,
  AvisoDeAprovacao,
  Digitando,
  MensagemDoAssistente,
  MensagemDoCliente,
  NotaDeSistema,
  RespostaEmConstrucao,
} from "./Mensagens";

type Props = Pick<
  EstadoDaConversa,
  "mensagens" | "emConstrucao" | "aguardando" | "acaoAtual" | "historicoCarregado"
> & {
  /** Evento da aprovação, "generica" quando só o status da Conversa diz que há uma, ou null. */
  aprovacao: EventoApprovalRequired | "generica" | null;
  status: StatusDaConversa | null;
};

/** Distância do fim (px) abaixo da qual a lista acompanha as mensagens novas. */
const PERTO_DO_FIM = 96;

export function ListaDeMensagens({
  mensagens,
  emConstrucao,
  aguardando,
  acaoAtual,
  historicoCarregado,
  aprovacao,
  status,
}: Props) {
  const rolagem = useRef<HTMLDivElement>(null);
  const grudadoNoFim = useRef(true);

  useLayoutEffect(() => {
    const elemento = rolagem.current;
    if (elemento && grudadoNoFim.current) elemento.scrollTop = elemento.scrollHeight;
  }, [mensagens, emConstrucao, aguardando, acaoAtual, aprovacao]);

  function aoRolar() {
    const elemento = rolagem.current;
    if (!elemento) return;
    grudadoNoFim.current =
      elemento.scrollHeight - elemento.scrollTop - elemento.clientHeight < PERTO_DO_FIM;
  }

  const ultimaEDoAssistente = mensagens.at(-1)?.papel === "assistente";

  return (
    <div ref={rolagem} onScroll={aoRolar} className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[760px] px-4 pt-8 pb-10 sm:px-6">
        {!historicoCarregado && mensagens.length === 0 ? (
          <CarregandoMensagens />
        ) : (
          <ol role="log" aria-label="Mensagens da Conversa" className="flex flex-col gap-7">
            {mensagens.map((mensagem) =>
              mensagem.papel === "cliente" ? (
                <MensagemDoCliente key={mensagem.id} mensagem={mensagem} />
              ) : (
                <MensagemDoAssistente key={mensagem.id} mensagem={mensagem} />
              ),
            )}
            {emConstrucao !== null && <RespostaEmConstrucao texto={emConstrucao} />}
            {acaoAtual && <AcaoEmAndamento nome={acaoAtual.nome} args={acaoAtual.args} />}
            {aguardando && emConstrucao === null && !acaoAtual && <Digitando />}
            {aprovacao && (
              <AvisoDeAprovacao aprovacao={aprovacao === "generica" ? null : aprovacao} />
            )}
            {status === "escalada" && ultimaEDoAssistente && !aguardando && (
              <NotaDeSistema>Esta Conversa foi encaminhada a um Atendente da Ampère.</NotaDeSistema>
            )}
          </ol>
        )}
      </div>
    </div>
  );
}

function CarregandoMensagens() {
  return (
    <div className="flex flex-col gap-8" aria-label="Carregando mensagens">
      <div className="flex justify-end">
        <Esqueleto className="h-10 w-56 rounded-[20px]" />
      </div>
      <div className="flex gap-3.5">
        <Esqueleto className="size-6 rounded-lg" />
        <div className="flex-1 space-y-2.5">
          <Esqueleto className="h-3.5 w-11/12" />
          <Esqueleto className="h-3.5 w-9/12" />
          <Esqueleto className="h-3.5 w-7/12" />
        </div>
      </div>
    </div>
  );
}
