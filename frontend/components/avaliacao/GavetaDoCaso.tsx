"use client";

import { X } from "lucide-react";
import type { ReactNode } from "react";
import type { Caso, CasoAgente, CasoJuiz, CasoRag, NomeDoEval } from "@/lib/api";
import { rotuloDoGrupo, segundos, temErro } from "@/lib/avaliacao";
import { cx } from "@/lib/cx";
import { TextoMarkdown } from "@/components/chat/Mensagens";
import { iconeDoNo } from "@/components/icones";
import { Aviso } from "@/components/ui/Aviso";
import { BotaoDeIcone } from "@/components/ui/Botao";
import { Gaveta } from "@/components/ui/Gaveta";
import { CONFERENCIAS, Quadrinho, Voz } from "./Quadrinho";

type Props = { nome: NomeDoEval; caso: Caso | null; aoFechar: () => void };

/** O detalhe de um caso, da execução completa ou da amostra: o mesmo esqueleto nas três abas. */
export function GavetaDoCaso({ nome, caso, aoFechar }: Props) {
  return (
    <Gaveta aberta={caso !== null} aoFechar={aoFechar} rotulo="Detalhe do caso" largura="max-w-xl">
      {caso && (
        <>
          <div className="flex items-start gap-3 border-b border-line px-5 pt-5 pb-4">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap gap-1.5">
                <Etiqueta>{caso.id}</Etiqueta>
                <Etiqueta>{rotuloDoGrupo(caso.grupo)}</Etiqueta>
                {"conjunto" in caso && <Etiqueta>{(caso as CasoJuiz).conjunto}</Etiqueta>}
              </div>
              <h2 className="mt-2 text-[17px] leading-snug font-semibold tracking-[-0.015em]">“{caso.texto}”</h2>
            </div>
            <BotaoDeIcone icone={X} rotulo="Fechar" onClick={aoFechar} />
          </div>
          <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
            {temErro(caso) ? (
              <Aviso>Este caso falhou: {caso.erro}</Aviso>
            ) : nome === "agente" ? (
              <DoAgente caso={caso as CasoAgente} />
            ) : nome === "rag" ? (
              <DaBusca caso={caso as CasoRag} />
            ) : (
              <DoJuiz caso={caso as CasoJuiz} />
            )}
            <p className="font-mono text-[11px] text-muted">levou {segundos(caso.duracao_s)}</p>
          </div>
        </>
      )}
    </Gaveta>
  );
}

/** Uma etiqueta neutra em mono, para ids e rótulos curtos. */
export function Etiqueta({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[10.5px] text-ink-2 ring-1 ring-line ring-inset">
      {children}
    </span>
  );
}

function Bloco({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="sobretitulo mb-2">{titulo}</h3>
      {children}
    </section>
  );
}

function Balao({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-xl bg-canvas px-3.5 py-3 text-[13.5px] leading-relaxed whitespace-pre-line text-ink-2">
      {children}
    </p>
  );
}

/** A resposta gerada é markdown de verdade: mesmo renderizador e estilo do chat. */
function BalaoMarkdown({ texto }: { texto: string }) {
  return (
    <div className="rounded-xl bg-canvas px-3.5 py-3">
      <TextoMarkdown texto={texto} />
    </div>
  );
}

function DoAgente({ caso }: { caso: CasoAgente }) {
  return (
    <>
      <Bloco titulo="Esperado contra obtido">
        <div className="divide-y divide-line">
          {CONFERENCIAS.map(([chave, rotulo]) => (
            <div key={chave} className="grid grid-cols-[84px_1fr_1fr_24px] items-center gap-2 py-2 text-[13px]">
              <span className="sobretitulo">{rotulo}</span>
              <span className="text-ink-2">{caso.esperado[chave] ?? "bloqueio"}</span>
              <span className={cx("font-semibold", !caso.ok[chave] && "text-perigo")}>{caso.obtido[chave]}</span>
              <Quadrinho ok={caso.ok[chave]} rotulo={rotulo} tamanho="sm" />
            </div>
          ))}
        </div>
      </Bloco>
      <Bloco titulo="Caminho no grafo">
        <ol className="flex flex-wrap items-center gap-1.5">
          {caso.caminho.map((no, indice) => {
            const Icone = iconeDoNo(no);
            return (
              <li key={`${no}-${indice}`} className="flex items-center gap-1.5">
                {indice > 0 && (
                  <span aria-hidden className="text-muted">
                    →
                  </span>
                )}
                <span className="inline-flex items-center gap-1 rounded-md bg-surface-2 px-1.5 py-1 font-mono text-[10.5px] text-ink-2 ring-1 ring-line ring-inset">
                  <Icone aria-hidden className="size-3" strokeWidth={1.8} />
                  {no}
                </span>
              </li>
            );
          })}
        </ol>
      </Bloco>
      <Bloco titulo="Resposta final">
        {caso.resposta ? (
          <BalaoMarkdown texto={caso.resposta} />
        ) : (
          <p className="text-[13px] text-muted">Sem resposta final: o turno parou numa Aprovação Pendente.</p>
        )}
      </Bloco>
      {caso.juiz && <Voz quem="Juiz" veredito={caso.juiz} />}
    </>
  );
}

function DaBusca({ caso }: { caso: CasoRag }) {
  const filtro = Object.entries(caso.filtro ?? {});
  return (
    <>
      <Bloco titulo="Filtro do self-querying">
        {filtro.length > 0 ? (
          <p className="rounded-lg bg-noite px-3 py-2 font-mono text-[12px] text-noite-texto">
            {filtro.map(([campo, valor], indice) => (
              <span key={campo}>
                {indice > 0 && " · "}
                {campo} = <span className="text-volt">{String(valor)}</span>
              </span>
            ))}
          </p>
        ) : (
          <p className="text-[13px] text-muted">Sem filtro: a busca olhou a Base de Conhecimento inteira.</p>
        )}
      </Bloco>
      <Bloco titulo="Os documentos que voltaram">
        <ol className="space-y-1">
          {caso.recuperados.map((documento, indice) => {
            const certo = documento === caso.documento_esperado;
            return (
              <li
                key={documento}
                className={cx(
                  "flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13px]",
                  certo && "bg-volt/30 font-semibold ring-1 ring-volt-forte ring-inset",
                )}
              >
                <span className="w-4 font-mono text-[11px] text-muted">{indice + 1}</span>
                {documento}
                {certo && <span className="ml-auto font-mono text-[10px]">o certo</span>}
              </li>
            );
          })}
          {caso.posicao === null && (
            <li className="mt-2 flex items-center gap-2 rounded-lg bg-perigo-soft px-2.5 py-1.5 text-[13px] text-perigo">
              <span className="w-4 font-mono text-[11px]">–</span>
              {caso.documento_esperado}
              <span className="ml-auto font-mono text-[10px]">o certo · fora do top 5</span>
            </li>
          )}
        </ol>
      </Bloco>
      <Bloco titulo="Resposta gerada">
        {caso.resposta ? (
          <BalaoMarkdown texto={caso.resposta} />
        ) : (
          <p className="text-[13px] text-muted">A geração não rodou nesta execução.</p>
        )}
      </Bloco>
      {caso.fidelidade && caso.relevancia && (
        <div className="grid gap-2 sm:grid-cols-2">
          <Voz quem="Fidelidade" veredito={caso.fidelidade} />
          <Voz quem="Relevância" veredito={caso.relevancia} />
        </div>
      )}
    </>
  );
}

function DoJuiz({ caso }: { caso: CasoJuiz }) {
  return (
    <>
      <Bloco titulo="Resposta julgada">
        <Balao>{caso.resposta}</Balao>
      </Bloco>
      <div className="grid gap-2 sm:grid-cols-2">
        <Voz quem="Humano" veredito={caso.humano} />
        <Voz quem="Juiz" veredito={caso.juiz} />
      </div>
      <p className={cx("text-[13px] font-medium", caso.concorda ? "text-sucesso" : "text-perigo")}>
        {caso.concorda ? "✓ Juiz e humano concordaram." : "✗ Juiz e humano discordaram."}
      </p>
    </>
  );
}
