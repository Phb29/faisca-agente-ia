"use client";

import {
  Banknote,
  BookOpenText,
  Headset,
  PackageSearch,
  Truck,
  type LucideIcon,
} from "lucide-react";
import type { Pedido } from "@/lib/api";
import { formatarReais, primeiroNome } from "@/lib/formatos";
import { Marca } from "@/components/ui/Marca";

type Sugestao = { texto: string; contexto: string; icone: LucideIcon };

const DUVIDAS: Sugestao[] = [
  { texto: "Qual o prazo de troca de um celular?", contexto: "Políticas da Loja", icone: BookOpenText },
  { texto: "Quanto tempo leva o frete de um notebook?", contexto: "Políticas da Loja", icone: Truck },
];

const FALAR_COM_PESSOA: Sugestao = {
  texto: "Quero falar com uma pessoa",
  contexto: "Atendimento humano",
  icone: Headset,
};

/** Atalhos para a demonstração: os Pedidos do Cliente primeiro, depois dúvidas e um humano. */
function sugestoesPara(pedidos: Pedido[]): Sugestao[] {
  const emTransporte = pedidos.find((p) => p.status === "em_transporte");
  const entregue = pedidos.find((p) => p.status === "entregue");
  const doCliente: Sugestao[] = [];
  if (emTransporte) {
    doCliente.push({
      texto: `Qual o status do pedido ${emTransporte.id}?`,
      contexto: emTransporte.produto,
      icone: PackageSearch,
    });
  }
  if (entregue) {
    doCliente.push({
      texto: `Quero reembolso do pedido ${entregue.id}`,
      contexto: `${entregue.produto} · ${formatarReais(entregue.valor)}`,
      icone: Banknote,
    });
  }
  return [...doCliente, ...DUVIDAS].slice(0, 3).concat(FALAR_COM_PESSOA);
}

type Props = {
  nome: string;
  clienteNovo: boolean;
  pedidos: Pedido[];
  aoEscolher: (texto: string) => void;
};

export function BoasVindas({ nome, clienteNovo, pedidos, aoEscolher }: Props) {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 py-10 sm:px-8">
      <div className="m-auto w-full max-w-[700px]">
        <Marca tamanho="lg" className="animate-surgir" />
        <h1 className="mt-7 animate-surgir font-display text-[clamp(32px,4.4vw,44px)] leading-[1.08] font-semibold tracking-[-0.04em] [animation-delay:60ms]">
          {clienteNovo ? "Olá." : `Olá, ${primeiroNome(nome)}.`}
          <span className="block text-muted">Como podemos ajudar?</span>
        </h1>

        <ul className="mt-10 grid gap-3 sm:grid-cols-2">
          {sugestoesPara(pedidos).map((sugestao, indice) => (
            <li
              key={sugestao.texto}
              className="animate-surgir"
              style={{ animationDelay: `${140 + indice * 60}ms` }}
            >
              <button
                type="button"
                onClick={() => aoEscolher(sugestao.texto)}
                className="group flex h-full w-full flex-col gap-4 rounded-2xl bg-surface-2 p-4 text-left ring-1 ring-line transition duration-200 ring-inset hover:bg-surface hover:shadow-elevada hover:ring-line-strong"
              >
                <span className="flex size-8 items-center justify-center rounded-lg bg-surface text-ink-2 ring-1 ring-line transition-colors ring-inset group-hover:bg-noite group-hover:text-volt group-hover:ring-noite">
                  <sugestao.icone aria-hidden className="size-4" strokeWidth={1.7} />
                </span>
                <span>
                  <span className="block text-[14.5px] leading-snug font-medium text-ink">{sugestao.texto}</span>
                  <span className="mt-1 block truncate text-[12.5px] text-muted">{sugestao.contexto}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
