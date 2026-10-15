"use client";

import { Hourglass } from "lucide-react";
import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { NomeDaAcao } from "@/lib/api";
import { cx } from "@/lib/cx";
import { formatarHora, formatarReais } from "@/lib/formatos";
import { acao, motivoDoGate } from "@/lib/rotulos";
import type { EventoApprovalRequired } from "@/lib/sse";
import type { MensagemNaTela } from "@/hooks/useConversa";
import { iconeDaAcao } from "@/components/icones";
import { Carregando } from "@/components/ui/Carregando";
import { Marca } from "@/components/ui/Marca";
import { Pilula, Ponto } from "@/components/ui/Pilula";

const PLUGINS = [remarkGfm];

export function TextoMarkdown({ texto, escrevendo = false }: { texto: string; escrevendo?: boolean }) {
  return (
    <div className={cx("texto-markdown", escrevendo && "escrevendo")}>
      <ReactMarkdown
        remarkPlugins={PLUGINS}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {texto}
      </ReactMarkdown>
    </div>
  );
}

export function MensagemDoCliente({ mensagem }: { mensagem: MensagemNaTela }) {
  return (
    <li className="flex animate-surgir flex-col items-end">
      <span className="sr-only">Você disse:</span>
      <div className="max-w-[85%] rounded-[20px] rounded-br-md bg-ink px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap text-canvas shadow-suave [overflow-wrap:anywhere]">
        {mensagem.conteudo}
      </div>
      <span className="mt-1.5 flex items-center gap-1.5 pr-1 font-mono text-[10.5px] text-muted">
        {mensagem.pendente ? (
          <>
            <Carregando className="size-2.5" rotulo="Enviando" /> enviando
          </>
        ) : (
          <time dateTime={mensagem.criada_em}>{formatarHora(mensagem.criada_em)}</time>
        )}
      </span>
    </li>
  );
}

/** Linha do assistente: sem balão, direto sobre a página, com a marca à esquerda. */
function LinhaDoAssistente({ children, momento }: { children: ReactNode; momento?: string }) {
  return (
    <li className="flex animate-surgir gap-3.5">
      <Marca tamanho="xs" className="mt-[3px]" />
      <div className="min-w-0 flex-1">
        <p className="mb-1 flex items-baseline gap-2">
          <span className="text-[13px] font-medium text-ink">Ampère</span>
          {momento && (
            <time dateTime={momento} className="font-mono text-[10.5px] text-muted">
              {formatarHora(momento)}
            </time>
          )}
        </p>
        {children}
      </div>
    </li>
  );
}

export function MensagemDoAssistente({ mensagem }: { mensagem: MensagemNaTela }) {
  return (
    <LinhaDoAssistente momento={mensagem.criada_em}>
      <TextoMarkdown texto={mensagem.conteudo} />
    </LinhaDoAssistente>
  );
}

export function RespostaEmConstrucao({ texto }: { texto: string }) {
  return (
    <LinhaDoAssistente>
      <div aria-busy="true">
        <TextoMarkdown texto={texto} escrevendo />
      </div>
    </LinhaDoAssistente>
  );
}

export function Digitando() {
  return (
    <LinhaDoAssistente>
      <span className="flex h-7 items-center gap-1" role="status">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            aria-hidden
            className="size-1.5 animate-onda rounded-full bg-ink-2"
            style={{ animationDelay: `${i * 0.16}s` }}
          />
        ))}
        <span className="sr-only">O assistente está pensando</span>
      </span>
    </LinhaDoAssistente>
  );
}

function detalheDosArgs(args: Record<string, unknown>): string | null {
  const valor = args.pedido_id ?? args.pergunta ?? args.motivo;
  return typeof valor === "string" && valor ? valor : null;
}

export function AcaoEmAndamento({ nome, args }: { nome: NomeDaAcao; args: Record<string, unknown> }) {
  const Icone = iconeDaAcao(nome);
  const detalhe = detalheDosArgs(args);
  return (
    <li className="flex animate-surgir items-center gap-3.5 pl-[1px]" role="status">
      <span className="relative flex size-6 items-center justify-center rounded-lg bg-surface-2 ring-1 ring-line ring-inset">
        <Icone aria-hidden className="size-3.5 text-ink-2" strokeWidth={1.8} />
        <Ponto tom="volt" pulsando className="absolute -top-0.5 -right-0.5" />
      </span>
      <span className="min-w-0 truncate text-[13.5px]">
        <span className="texto-brilhante font-medium">{acao(nome).andamento}</span>
        {detalhe && <span className="font-mono text-[12px] text-muted"> · {detalhe}</span>}
      </span>
    </li>
  );
}

type PropsDaAprovacao = { aprovacao: EventoApprovalRequired | null };

/** Reembolso congelado à espera do Atendente. Sem o evento (Conversa reaberta), mostra o genérico. */
export function AvisoDeAprovacao({ aprovacao }: PropsDaAprovacao) {
  return (
    <li className="animate-surgir">
      <div className="moldura-listrada rounded-2xl p-[1.5px] shadow-elevada">
        <div className="rounded-[15px] bg-surface p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="sobretitulo flex items-center gap-1.5 text-alerta">
                <Hourglass aria-hidden className="size-3.5" strokeWidth={2} /> Aprovação pendente
              </p>
              {aprovacao && (
                <>
                  <p className="mt-3 font-display text-[32px] leading-none font-semibold tracking-[-0.035em] tabular-nums">
                    {formatarReais(aprovacao.valor)}
                  </p>
                  <p className="mt-2 text-[13px] text-muted">
                    Reembolso do Pedido <span className="font-mono text-ink-2">{aprovacao.pedido_id}</span>
                  </p>
                </>
              )}
            </div>
            {aprovacao?.motivo_do_gate && <Pilula tom="alerta">{motivoDoGate(aprovacao.motivo_do_gate)}</Pilula>}
          </div>
          <p className="mt-4 text-[14px] leading-relaxed text-ink-2">
            {aprovacao
              ? "Este Reembolso precisa da aprovação de um Atendente. A resposta chega aqui mesmo, nesta Conversa, assim que ele decidir."
              : "Um Reembolso desta Conversa aguarda a decisão de um Atendente. A resposta chega aqui mesmo, assim que ele decidir."}
          </p>
        </div>
      </div>
    </li>
  );
}

export function NotaDeSistema({ children }: { children: ReactNode }) {
  return (
    <li className="flex animate-surgir items-center gap-3 text-[12.5px] text-muted">
      <span className="h-px flex-1 bg-line" />
      <span className="max-w-[80%] text-center">{children}</span>
      <span className="h-px flex-1 bg-line" />
    </li>
  );
}
