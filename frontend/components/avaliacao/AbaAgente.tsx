"use client";

import type { Caso, CasoAgente, Execucao, ResumoAgente } from "@/lib/api";
import { porcento, rotuloDoGrupo, temErro } from "@/lib/avaliacao";
import { Pilula } from "@/components/ui/Pilula";
import { Numeros } from "./Numeros";
import { QuadrinhosDoAgente } from "./Quadrinho";
import { Quadro } from "./Quadro";

const ORDEM_DOS_GRUPOS = ["duvida", "transacao", "quer_humano", "bloqueio"];
const CONFERENCIAS = [
  ["intencao", "Intenção"],
  ["acao", "Ação"],
  ["desfecho", "Desfecho"],
] as const;

type Props = { execucao: Execucao; aoAbrirCaso: (caso: Caso) => void };

export function AbaAgente({ execucao, aoAbrirCaso }: Props) {
  const resumo = execucao.resumo as ResumoAgente | null;
  const casos = execucao.casos ?? [];
  const validos = casos.filter((caso) => !temErro(caso)) as CasoAgente[];
  const certos = (chave: (typeof CONFERENCIAS)[number][0]) => validos.filter((c) => c.ok[chave]).length;

  return (
    <div className="animate-surgir space-y-4 [animation-delay:60ms]">
      <Numeros
        itens={[
          {
            rotulo: "Intenção",
            valor: porcento(resumo?.intencao),
            sufixo: resumo ? "%" : undefined,
            detalhe: `${certos("intencao")} de ${validos.length} no Roteador`,
          },
          {
            rotulo: "Ação",
            valor: porcento(resumo?.acao),
            sufixo: resumo ? "%" : undefined,
            detalhe: `${certos("acao")} de ${validos.length} escolheram a Ação certa`,
          },
          {
            rotulo: "Desfecho",
            valor: porcento(resumo?.desfecho),
            sufixo: resumo ? "%" : undefined,
            detalhe: `${certos("desfecho")} de ${validos.length} terminaram como esperado`,
          },
          {
            rotulo: "Juiz aprovou",
            valor: resumo ? String(resumo.juiz_aprovadas) : "—",
            sufixo: resumo ? `/${resumo.julgados}` : undefined,
            detalhe: "respostas finais com texto",
          },
        ]}
      />
      <div className="grid gap-4 xl:grid-cols-[1.25fr_1fr]">
        <Cenarios casos={casos} aoAbrirCaso={aoAbrirCaso} />
        <OndeErrou casos={casos} aoAbrirCaso={aoAbrirCaso} />
      </div>
    </div>
  );
}

/** Os grupos na ordem combinada, com qualquer grupo fora de `ORDEM_DOS_GRUPOS` ao final,
 * na ordem em que aparece nos casos (nenhum grupo some por não estar previsto). */
function agruparPorGrupo(casos: Caso[]): { grupo: string; lista: Caso[] }[] {
  const previstos = new Set<string>(ORDEM_DOS_GRUPOS);
  const extras: string[] = [];
  for (const caso of casos) {
    if (!previstos.has(caso.grupo) && !extras.includes(caso.grupo)) extras.push(caso.grupo);
  }
  return [...ORDEM_DOS_GRUPOS, ...extras]
    .map((grupo) => ({ grupo, lista: casos.filter((caso) => caso.grupo === grupo) }))
    .filter(({ lista }) => lista.length > 0);
}

function Cenarios({ casos, aoAbrirCaso }: { casos: Caso[]; aoAbrirCaso: (caso: Caso) => void }) {
  const grupos = agruparPorGrupo(casos);

  return (
    <Quadro
      id="titulo-cenarios"
      titulo="Cenários"
      descricao="Um quadrado por conferência. Vermelho com ✗ é onde errou."
    >
      {grupos.length === 0 ? (
        <p className="mt-6 text-[13px] text-muted">Nenhum cenário nesta execução.</p>
      ) : (
        <div className="mt-2 max-h-[520px] overflow-y-auto pr-1">
          <div
            aria-hidden
            className="sticky top-0 z-10 flex items-center gap-3 bg-surface px-1 py-1 font-mono text-[9px] text-muted"
          >
            <span className="min-w-0 flex-1" />
            <span className="flex shrink-0 gap-1.5">
              {["INT", "AÇÃO", "DESF", "JUIZ"].map((rotulo) => (
                <span key={rotulo} className="w-6 text-center">
                  {rotulo}
                </span>
              ))}
            </span>
          </div>
          {grupos.map(({ grupo, lista }) => (
            <div key={grupo}>
              <p className="sobretitulo pt-3 pb-1">
                {rotuloDoGrupo(grupo)} · {lista.length}
              </p>
              <ul className="divide-y divide-line">
                {lista.map((caso) => (
                  <li key={caso.id}>
                    <button
                      type="button"
                      onClick={() => aoAbrirCaso(caso)}
                      className="flex w-full items-center gap-3 rounded-md px-1 py-2 text-left text-[13px] transition-colors hover:bg-surface-2"
                    >
                      <span className="rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[10.5px] text-ink-2 ring-1 ring-line ring-inset">
                        {caso.id}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-ink-2">{caso.texto}</span>
                      <QuadrinhosDoAgente caso={caso} />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Quadro>
  );
}

function errou(caso: Caso): boolean {
  if (temErro(caso)) return true;
  const c = caso as CasoAgente;
  return !Object.values(c.ok).every(Boolean) || c.juiz?.aprovada === false;
}

function OndeErrou({ casos, aoAbrirCaso }: { casos: Caso[]; aoAbrirCaso: (caso: Caso) => void }) {
  const erros = casos.filter(errou);
  return (
    <Quadro
      id="titulo-onde-errou"
      titulo="Onde errou"
      descricao="O esperado contra o que o grafo fez, com a crítica do juiz."
    >
      {erros.length === 0 ? (
        <p className="mt-6 text-[13px] text-muted">Nenhum erro nesta execução.</p>
      ) : (
        <ul className="mt-2 max-h-[520px] divide-y divide-line overflow-y-auto pr-1">
          {erros.map((caso) => (
            <li key={caso.id}>
              <button
                type="button"
                onClick={() => aoAbrirCaso(caso)}
                className="w-full rounded-md px-1 py-3 text-left transition-colors hover:bg-surface-2"
              >
                <ErroDoCaso caso={caso} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Quadro>
  );
}

function ErroDoCaso({ caso }: { caso: Caso }) {
  const id = (
    <span className="rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[10.5px] text-ink-2 ring-1 ring-line ring-inset">
      {caso.id}
    </span>
  );
  if (temErro(caso)) {
    return (
      <>
        <span className="flex items-center gap-2">
          {id}
          <Pilula tom="perigo">falhou</Pilula>
        </span>
        <span className="mt-1.5 block text-[12.5px] text-perigo">{caso.erro}</span>
      </>
    );
  }
  const c = caso as CasoAgente;
  const errados = CONFERENCIAS.filter(([chave]) => !c.ok[chave]);
  return (
    <>
      <span className="flex flex-wrap items-center gap-2">
        {id}
        {errados.map(([chave, rotulo]) => (
          <Pilula key={chave} tom="perigo">
            {rotulo}
          </Pilula>
        ))}
        {c.juiz?.aprovada === false && <Pilula tom="perigo">Juiz</Pilula>}
      </span>
      <span className="mt-1.5 block text-[13px] leading-snug">“{c.texto}”</span>
      {errados.map(([chave, rotulo]) => (
        <span key={chave} className="mt-1 block text-[12.5px] text-ink-2">
          {rotulo}: esperado <b>{c.esperado[chave] ?? "bloqueio"}</b> · obtido{" "}
          <span className="text-muted line-through">{c.obtido[chave]}</span>
        </span>
      ))}
      {c.juiz?.aprovada === false && (
        <span className="mt-2 block rounded-lg bg-canvas px-3 py-2 text-[12.5px] leading-relaxed text-ink-2">
          “{c.juiz.critica}”
        </span>
      )}
    </>
  );
}
