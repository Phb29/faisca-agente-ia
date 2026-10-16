"use client";

import Link from "next/link";
import { ArrowRight, ChevronRight, RefreshCw, UserPlus } from "lucide-react";
import { listarClientes, mensagemDeErro, type Cliente } from "@/lib/api";
import { gerarId } from "@/lib/id";
import { useRecurso } from "@/hooks/useRecurso";
import { Avatar } from "@/components/ui/Avatar";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { Logotipo } from "@/components/ui/Marca";
import { Esqueleto } from "@/components/ui/Vazio";

export type ClienteEscolhido = { id: string; nome: string; novo?: boolean };

type Props = { aoEscolher: (cliente: ClienteEscolhido) => void };

/** Primeira tela do chat, depois do login: quem é o Cliente desta sessão. O Cliente é de
 * exemplo e não tem login próprio, de propósito; o login é da equipe que usa o app. */
export function TelaDeEntrada({ aoEscolher }: Props) {
  const clientes = useRecurso("clientes", listarClientes);

  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1.08fr)_minmax(0,1fr)]">
      <PainelDaMarca />

      <main className="flex flex-col px-5 py-8 sm:px-10 lg:justify-center lg:py-12">
        <div className="lg:hidden">
          <Logotipo subtitulo="Suporte" />
        </div>

        <div className="mx-auto mt-14 w-full max-w-[420px] lg:mt-0">
          <p className="sobretitulo animate-surgir">Suporte ao Cliente</p>
          <h1 className="mt-3 animate-surgir font-display text-[36px] leading-[1.08] font-semibold tracking-[-0.04em] [animation-delay:60ms]">
            Quem está falando?
          </h1>
          <p className="mt-3 animate-surgir text-[15px] leading-relaxed text-muted [animation-delay:120ms]">
            Escolha um Cliente fictício. Cada um tem Pedidos, Conversas e memória próprios.
          </p>

          <div className="mt-8">
            {clientes.erro ? (
              <Aviso
                acao={
                  <button
                    type="button"
                    onClick={() => void clientes.recarregar()}
                    className="inline-flex items-center gap-1 font-medium underline-offset-2 hover:underline"
                  >
                    <RefreshCw aria-hidden className="size-3.5" /> Tentar de novo
                  </button>
                }
              >
                Não foi possível carregar os Clientes. {mensagemDeErro(clientes.erro)}
              </Aviso>
            ) : (
              <ListaDeClientes clientes={clientes.dados} aoEscolher={aoEscolher} />
            )}
          </div>

          <div className="my-6 flex items-center gap-3 text-[12px] text-muted">
            <span className="h-px flex-1 bg-line" />
            ou
            <span className="h-px flex-1 bg-line" />
          </div>

          <Botao
            variante="secundario"
            tamanho="lg"
            icone={UserPlus}
            className="w-full"
            onClick={() => aoEscolher({ id: gerarId("cli_"), nome: "Cliente novo", novo: true })}
          >
            Entrar como Cliente novo
          </Botao>

          <p className="mt-12 text-center text-[13px] text-muted">
            É da equipe da Loja?{" "}
            <Link
              href="/atendente"
              className="inline-flex items-center gap-1 font-medium text-ink underline-offset-4 hover:underline"
            >
              Central do Atendente <ArrowRight aria-hidden className="size-3.5" />
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}

function ListaDeClientes({
  clientes,
  aoEscolher,
}: {
  clientes: Cliente[] | null;
  aoEscolher: Props["aoEscolher"];
}) {
  if (clientes === null) {
    return (
      <ul className="space-y-2.5" aria-label="Carregando Clientes">
        {[0, 1, 2].map((i) => (
          <li key={i} className="flex items-center gap-3.5 rounded-2xl bg-surface p-3.5 ring-1 ring-line">
            <Esqueleto className="size-11 rounded-full" />
            <span className="flex-1 space-y-2">
              <Esqueleto className="h-3.5 w-32" />
              <Esqueleto className="h-3 w-44" />
            </span>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <ul className="space-y-2.5">
      {clientes.map((cliente, indice) => (
        <li key={cliente.id} className="animate-surgir" style={{ animationDelay: `${160 + indice * 60}ms` }}>
          <button
            type="button"
            onClick={() => aoEscolher({ id: cliente.id, nome: cliente.nome })}
            className="group flex w-full items-center gap-3.5 rounded-2xl bg-surface p-3.5 pr-4 text-left shadow-suave ring-1 ring-line transition duration-200 hover:-translate-y-px hover:shadow-elevada hover:ring-line-strong"
          >
            <Avatar nome={cliente.nome} semente={cliente.id} tamanho="lg" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[15px] font-medium">{cliente.nome}</span>
              <span className="block truncate text-[13px] text-muted">{cliente.email}</span>
            </span>
            <span className="hidden font-mono text-[11px] text-muted sm:inline">{cliente.id}</span>
            <ChevronRight
              aria-hidden
              className="size-4 text-muted transition group-hover:translate-x-0.5 group-hover:text-ink"
            />
          </button>
        </li>
      ))}
    </ul>
  );
}

const PILARES = [
  { titulo: "Guardrails", texto: "Cada mensagem é checada na entrada e na saída." },
  { titulo: "Memória", texto: "Fatos, histórico e instruções de cada Cliente." },
  { titulo: "Humano no circuito", texto: "Reembolsos críticos passam por um Atendente." },
];

function PainelDaMarca() {
  return (
    <aside className="relative hidden overflow-hidden bg-noite p-12 text-noite-texto lg:flex lg:flex-col lg:justify-between">
      <div aria-hidden className="grade-fina absolute inset-0" />
      <div aria-hidden className="grao absolute inset-0" />
      <Circuito />

      <div className="relative">
        <Logotipo subtitulo="Suporte" claro />
      </div>

      <div className="relative max-w-[540px]">
        <p className="sobretitulo animate-surgir text-noite-muted">Ampère Eletrônicos</p>
        <h2 className="mt-5 animate-surgir font-display text-[clamp(48px,5vw,68px)] leading-[1] font-semibold tracking-[-0.045em] [animation-delay:80ms]">
          Atendimento
          <br />
          que <span className="text-volt">resolve.</span>
        </h2>
        <p className="mt-6 max-w-md animate-surgir text-[15px] leading-relaxed text-noite-muted [animation-delay:160ms]">
          Dúvidas de política, Pedidos, Reembolsos e Tickets numa só conversa, com um Atendente
          humano sempre que o caso pede.
        </p>
      </div>

      <dl className="relative grid grid-cols-3 gap-8 border-t border-noite-line pt-6">
        {PILARES.map((pilar) => (
          <div key={pilar.titulo}>
            <dt className="text-[13px] font-medium">{pilar.titulo}</dt>
            <dd className="mt-1 text-[12.5px] leading-relaxed text-noite-muted">{pilar.texto}</dd>
          </div>
        ))}
      </dl>
    </aside>
  );
}

/** Trilhas de circuito com uma corrente volt passando: o único ornamento da marca. */
function Circuito() {
  const trilhas = [
    "M600 96 H468 L428 136 V236 L388 276 H250",
    "M600 214 H524 L484 254 V372 L444 412 H318",
    "M352 -10 V52 L392 92 H600",
    "M600 330 H560 L540 350 V470",
  ];
  const nos = [
    [428, 136],
    [388, 276],
    [484, 254],
    [444, 412],
    [392, 92],
    [540, 350],
  ];
  return (
    <svg
      aria-hidden
      viewBox="0 0 600 520"
      preserveAspectRatio="xMaxYMin meet"
      className="absolute top-0 right-0 h-[72%] w-auto opacity-80 [mask-image:linear-gradient(to_left,black_40%,transparent_95%)]"
      fill="none"
    >
      {trilhas.map((d) => (
        <path key={d} d={d} stroke="var(--noite-line)" strokeWidth="1.2" />
      ))}
      {trilhas.map((d, i) => (
        <path
          key={`${d}-corrente`}
          d={d}
          stroke="var(--volt)"
          strokeWidth="1.6"
          strokeLinecap="round"
          className="fluxo-eletrico"
          style={{ animationDelay: `${i * -0.9}s` }}
        />
      ))}
      {nos.map(([x, y]) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r="3" fill="var(--noite)" stroke="var(--noite-muted)" />
      ))}
    </svg>
  );
}
