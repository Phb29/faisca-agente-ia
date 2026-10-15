"use client";

import { Check, Inbox, X } from "lucide-react";
import { useId, useState } from "react";
import { aprovarReembolso, rejeitarReembolso, type Aprovacao } from "@/lib/api";
import { cx } from "@/lib/cx";
import { formatarPorcentagem, formatarReais, formatarRelativo } from "@/lib/formatos";
import { motivoDoGate } from "@/lib/rotulos";
import { Botao } from "@/components/ui/Botao";
import { CabecalhoDeSecao } from "@/components/ui/CabecalhoDeSecao";
import { Pilula } from "@/components/ui/Pilula";
import { Esqueleto, Vazio } from "@/components/ui/Vazio";

/** Limiar do Gate só para desenhar a marca no medidor; quem decide é a API. */
const LIMIAR_VISUAL = 0.5;

type Props = {
  token: string;
  aprovacoes: Aprovacao[] | null;
  aoDecidir: (mensagem: string) => void;
  aoErro: (erro: unknown) => void;
};

export function FilaDeAprovacoes({ token, aprovacoes, aoDecidir, aoErro }: Props) {
  return (
    <section aria-labelledby="titulo-aprovacoes">
      <CabecalhoDeSecao
        id="titulo-aprovacoes"
        titulo="Aprovações pendentes"
        descricao="Reembolsos que o Gate retirou do fluxo automático. A Conversa do Cliente fica congelada até a sua decisão."
        contagem={aprovacoes?.length}
      />
      {aprovacoes === null ? (
        <div className="grid gap-4 2xl:grid-cols-2">
          {[0, 1].map((i) => (
            <Esqueleto key={i} className="h-[260px] rounded-2xl" />
          ))}
        </div>
      ) : aprovacoes.length === 0 ? (
        <div className="rounded-2xl bg-surface ring-1 ring-line">
          <Vazio icone={Inbox} titulo="Nenhum Reembolso aguardando decisão">
            Quando o Gate de Aprovação pedir um humano, o caso aparece aqui na hora.
          </Vazio>
        </div>
      ) : (
        <ul className="grid gap-4 2xl:grid-cols-2">
          {aprovacoes.map((aprovacao) => (
            <CartaoDeAprovacao
              key={aprovacao.id}
              token={token}
              aprovacao={aprovacao}
              aoDecidir={aoDecidir}
              aoErro={aoErro}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

type PropsDoCartao = {
  token: string;
  aprovacao: Aprovacao;
  aoDecidir: (mensagem: string) => void;
  aoErro: (erro: unknown) => void;
};

function CartaoDeAprovacao({ token, aprovacao, aoDecidir, aoErro }: PropsDoCartao) {
  const idDoMotivo = useId();
  const [rejeitando, setRejeitando] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [ocupado, setOcupado] = useState<"aprovar" | "rejeitar" | null>(null);

  async function decidir(decisao: "aprovar" | "rejeitar") {
    setOcupado(decisao);
    try {
      if (decisao === "aprovar") {
        await aprovarReembolso(token, aprovacao.id);
        aoDecidir(`Reembolso do Pedido ${aprovacao.pedido_id} aprovado. A Conversa foi retomada.`);
      } else {
        await rejeitarReembolso(token, aprovacao.id, motivo.trim() || undefined);
        aoDecidir(`Reembolso do Pedido ${aprovacao.pedido_id} rejeitado. O Cliente recebe o motivo na Conversa.`);
      }
    } catch (erro) {
      aoErro(erro);
      setOcupado(null);
    }
  }

  return (
    <li className="flex animate-surgir flex-col overflow-hidden rounded-2xl bg-surface shadow-suave ring-1 ring-line">
      <div className="flex-1 p-5 sm:p-6">
        <div className="flex items-center justify-between gap-3">
          {aprovacao.motivo_do_gate ? (
            <Pilula tom="alerta" ponto>
              {motivoDoGate(aprovacao.motivo_do_gate)}
            </Pilula>
          ) : (
            <span />
          )}
          <time dateTime={aprovacao.criada_em} className="font-mono text-[11px] text-muted">
            {formatarRelativo(aprovacao.criada_em)}
          </time>
        </div>

        <p className="mt-4 font-display text-[34px] leading-none font-semibold tracking-[-0.035em] tabular-nums">
          {formatarReais(aprovacao.valor)}
        </p>
        <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px] text-muted">
          Pedido <span className="font-mono text-ink-2">{aprovacao.pedido_id}</span>
          <span aria-hidden>·</span>
          Cliente <span className="font-mono text-ink-2">{aprovacao.cliente_id}</span>
        </p>
        <p className="mt-4 text-[13.5px] leading-relaxed text-ink-2">{aprovacao.resumo}</p>

        <MedidorDoGate probabilidade={aprovacao.probabilidade} />
      </div>

      <div className="border-t border-line bg-surface-2 px-5 py-4 sm:px-6">
        {rejeitando ? (
          <div className="animate-surgir">
            <label htmlFor={idDoMotivo} className="text-[12.5px] font-medium text-ink-2">
              Motivo da rejeição <span className="font-normal text-muted">(opcional, enviado ao Cliente)</span>
            </label>
            <textarea
              id={idDoMotivo}
              value={motivo}
              onChange={(evento) => setMotivo(evento.target.value)}
              rows={2}
              autoFocus
              placeholder="Ex.: o prazo de 7 dias para arrependimento já passou."
              className="mt-1.5 w-full resize-none rounded-xl bg-surface px-3 py-2 text-[13.5px] ring-1 ring-line outline-none ring-inset placeholder:text-muted focus:ring-[1.5px] focus:ring-ink/40"
            />
            <div className="mt-3 flex flex-wrap gap-2">
              <Botao variante="perigo" tamanho="sm" icone={X} carregando={ocupado === "rejeitar"} onClick={() => void decidir("rejeitar")}>
                Confirmar rejeição
              </Botao>
              <Botao variante="fantasma" tamanho="sm" disabled={ocupado !== null} onClick={() => setRejeitando(false)}>
                Cancelar
              </Botao>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Botao
              tamanho="sm"
              icone={Check}
              carregando={ocupado === "aprovar"}
              disabled={ocupado !== null}
              onClick={() => void decidir("aprovar")}
            >
              Aprovar Reembolso
            </Botao>
            <Botao variante="secundario" tamanho="sm" disabled={ocupado !== null} onClick={() => setRejeitando(true)}>
              Rejeitar
            </Botao>
          </div>
        )}
      </div>
    </li>
  );
}

function MedidorDoGate({ probabilidade }: { probabilidade: number }) {
  const acima = probabilidade >= LIMIAR_VISUAL;
  const porcentagem = Math.max(0, Math.min(1, probabilidade)) * 100;
  return (
    <div className="mt-5">
      <div className="flex items-baseline justify-between text-[12px]">
        <span className="text-muted">Probabilidade de ser crítico, segundo o Jev</span>
        <span className={cx("font-mono tabular-nums", acima ? "text-alerta" : "text-ink")}>
          {formatarPorcentagem(probabilidade)}
        </span>
      </div>
      <div
        role="meter"
        aria-label="Probabilidade do Gate de Aprovação"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(porcentagem)}
        className="relative mt-2 h-1.5 rounded-full bg-canvas-2 ring-1 ring-line ring-inset"
      >
        <span
          className={cx("absolute inset-y-0 left-0 rounded-full", acima ? "bg-alerta" : "bg-ink-2")}
          style={{ width: `${porcentagem}%` }}
        />
        <span
          aria-hidden
          className="absolute -top-1 -bottom-1 w-px bg-ink"
          style={{ left: `${LIMIAR_VISUAL * 100}%` }}
        />
      </div>
      <p className="mt-1.5 font-mono text-[10.5px] text-muted" style={{ paddingLeft: `calc(${LIMIAR_VISUAL * 100}% - 18px)` }}>
        limiar {formatarPorcentagem(LIMIAR_VISUAL)}
      </p>
    </div>
  );
}
