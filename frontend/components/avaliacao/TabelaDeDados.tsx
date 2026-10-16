"use client";

import { ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";
import type {
  ConjuntoDoJuiz,
  DadosDoEval,
  LinhaDaBusca,
  LinhaDoAgente,
  LinhaDoJuiz,
  LinhaDosDados,
  NomeDoEval,
} from "@/lib/api";
import { grupoNoPlural, rotuloDoGrupo, TEXTOS_DOS_DADOS } from "@/lib/avaliacao";
import { acao } from "@/lib/rotulos";
import type { Tom } from "@/lib/rotulos";
import { Pilula } from "@/components/ui/Pilula";
import { Segmentos } from "@/components/ui/Segmentos";
import { Esqueleto } from "@/components/ui/Vazio";
import { Etiqueta } from "./GavetaDoCaso";

const TODOS = "todos";
const CONJUNTOS: ConjuntoDoJuiz[] = ["treino", "dev", "teste"];

export const TOM_DO_DESFECHO: Record<string, Tom> = {
  Resolvida: "sucesso",
  Escalada: "info",
  "Aprovação Pendente": "alerta",
};

type Props = {
  nome: NomeDoEval;
  dados: DadosDoEval | null;
  aoAbrir: (linha: LinhaDosDados) => void;
};

/** O quadro de um golden: título, filtro por grupo (e por conjunto, no juiz) e a tabela. */
export function TabelaDeDados({ nome, dados, aoAbrir }: Props) {
  const [grupo, setGrupo] = useState(TODOS);
  const [conjunto, setConjunto] = useState<string>(TODOS);
  const textos = TEXTOS_DOS_DADOS[nome];

  const linhas = ((dados?.linhas ?? []) as LinhaDosDados[]).filter(
    (linha) =>
      (grupo === TODOS || linha.grupo === grupo) &&
      (conjunto === TODOS || ("conjunto" in linha && linha.conjunto === conjunto)),
  );

  return (
    <section
      aria-labelledby="titulo-dados"
      className="min-w-0 overflow-hidden rounded-2xl bg-surface shadow-suave ring-1 ring-line"
    >
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 p-5 pb-4">
        <div className="max-w-2xl min-w-0">
          <h2 id="titulo-dados" className="flex items-baseline gap-2.5 text-[15px] font-semibold tracking-[-0.01em]">
            {textos.titulo}
            <span className="font-mono text-[12px] font-normal text-muted">{linhas.length}</span>
          </h2>
          <p className="mt-1 text-[12.5px] leading-relaxed text-muted">{textos.descricao}</p>
        </div>
        {dados && (
          <div className="flex flex-wrap gap-2">
            <Segmentos
              rotulo="Filtrar por grupo"
              valor={grupo}
              aoMudar={setGrupo}
              opcoes={[
                { valor: TODOS, rotulo: comContagem(textos.todos, dados.n) },
                ...Object.entries(dados.grupos).map(([valor, quantidade]) => ({
                  valor,
                  rotulo: comContagem(grupoNoPlural(valor), quantidade),
                })),
              ]}
            />
            {dados.eval === "juiz" && (
              <Segmentos
                rotulo="Filtrar por conjunto"
                valor={conjunto}
                aoMudar={setConjunto}
                opcoes={[
                  { valor: TODOS, rotulo: "Todos" },
                  ...CONJUNTOS.map((valor) => ({
                    valor,
                    rotulo: comContagem(valor, dados.conjuntos[valor]),
                  })),
                ]}
              />
            )}
          </div>
        )}
      </div>

      {dados === null ? (
        <div className="divide-y divide-line border-t border-line">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="flex items-center gap-4 px-5 py-4">
              <Esqueleto className="h-3 w-12" />
              <Esqueleto className="h-3 flex-1" />
              <Esqueleto className="h-3 w-24" />
            </div>
          ))}
        </div>
      ) : linhas.length === 0 ? (
        <p className="border-t border-line px-5 py-8 text-[13px] text-muted">Nenhuma linha com esse filtro.</p>
      ) : (
        <table className="w-full table-fixed border-t border-line text-left">
          <thead className="border-b border-line bg-surface-2">
            <Cabecalho nome={nome} />
          </thead>
          <tbody className="divide-y divide-line">
            {linhas.map((linha) => (
              <Linha key={linha.id} nome={nome} linha={linha} aoAbrir={() => aoAbrir(linha)} />
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function comContagem(rotulo: string, quantidade: number): ReactNode {
  return (
    <>
      {rotulo}
      <span className="font-mono text-[10px] opacity-60">{quantidade}</span>
    </>
  );
}

const TH = "px-3 py-2.5 font-medium";

function Cabecalho({ nome }: { nome: NomeDoEval }) {
  const colunas: [string, string][] =
    nome === "rag"
      ? [
          ["Pergunta e resposta de referência", ""],
          ["Documento esperado", "hidden w-[210px] md:table-cell"],
          ["Origem", "w-[118px]"],
        ]
      : nome === "agente"
        ? [
            ["Mensagem do Cliente", ""],
            ["Intenção", "hidden w-[150px] md:table-cell"],
            ["Ação esperada", "hidden w-[170px] lg:table-cell"],
            ["Desfecho", "w-[156px]"],
          ]
        : [
            ["Mensagem e resposta do chatbot", ""],
            ["Humano", "w-[118px]"],
            ["Conjunto", "hidden w-[96px] sm:table-cell"],
          ];
  return (
    <tr className="sobretitulo">
      <th scope="col" className="w-[78px] py-2.5 pr-3 pl-5 font-medium">
        Id
      </th>
      {colunas.map(([rotulo, classe]) => (
        <th key={rotulo} scope="col" className={`${TH} ${classe}`}>
          {rotulo}
        </th>
      ))}
      <th scope="col" className="w-11 px-3 py-2.5">
        <span className="sr-only">Abrir</span>
      </th>
    </tr>
  );
}

type PropsDaLinha = { nome: NomeDoEval; linha: LinhaDosDados; aoAbrir: () => void };

function Linha({ nome, linha, aoAbrir }: PropsDaLinha) {
  return (
    <tr onClick={aoAbrir} className="group cursor-pointer align-top transition-colors hover:bg-surface-2">
      <td className="py-3.5 pr-3 pl-5 font-mono text-[11.5px] whitespace-nowrap text-muted">{linha.id}</td>
      {nome === "rag" ? (
        <CelulasDaBusca linha={linha as LinhaDaBusca} aoAbrir={aoAbrir} />
      ) : nome === "agente" ? (
        <CelulasDoAgente linha={linha as LinhaDoAgente} aoAbrir={aoAbrir} />
      ) : (
        <CelulasDoJuiz linha={linha as LinhaDoJuiz} aoAbrir={aoAbrir} />
      )}
      <td className="px-3 py-3.5 text-right">
        <ChevronRight
          aria-hidden
          className="ml-auto size-4 text-muted transition group-hover:translate-x-0.5 group-hover:text-ink"
        />
      </td>
    </tr>
  );
}

/** O texto principal da linha é o botão: quem navega pelo teclado abre a gaveta por ele. */
function Principal({ texto, aoAbrir, children }: { texto: string; aoAbrir: () => void; children?: ReactNode }) {
  return (
    <td className="px-3 py-3.5">
      <button
        type="button"
        onClick={(evento) => {
          evento.stopPropagation();
          aoAbrir();
        }}
        className="line-clamp-2 text-left text-[13.5px] leading-relaxed text-ink"
      >
        {texto}
      </button>
      {children}
    </td>
  );
}

function CelulasDaBusca({ linha, aoAbrir }: { linha: LinhaDaBusca; aoAbrir: () => void }) {
  return (
    <>
      <Principal texto={linha.pergunta} aoAbrir={aoAbrir}>
        <p className="mt-0.5 line-clamp-1 text-[12.5px] leading-relaxed text-muted">{linha.resposta_referencia}</p>
      </Principal>
      <td className="hidden px-3 py-3.5 md:table-cell">
        <span className="font-mono text-[12px] break-all text-ink-2">{linha.documento_esperado}</span>
      </td>
      <td className="px-3 py-3.5">
        <Pilula tom={linha.grupo === "adversarial" ? "info" : "neutro"}>{linha.grupo}</Pilula>
      </td>
    </>
  );
}

function CelulasDoAgente({ linha, aoAbrir }: { linha: LinhaDoAgente; aoAbrir: () => void }) {
  const quem = [linha.cliente_id, linha.pedido_id, linha.memorias && "com memória"].filter(Boolean).join(" · ");
  return (
    <>
      <Principal texto={linha.mensagem} aoAbrir={aoAbrir}>
        <p className="mt-0.5 font-mono text-[11px] text-muted">{quem}</p>
      </Principal>
      <td className="hidden px-3 py-3.5 md:table-cell">
        {linha.guardrail_bloqueia ? (
          <Pilula tom="perigo">Bloqueio</Pilula>
        ) : (
          <Pilula>{rotuloDoGrupo(linha.intencao_esperada ?? "bloqueio")}</Pilula>
        )}
      </td>
      <td className="hidden px-3 py-3.5 text-[12.5px] text-ink-2 lg:table-cell">
        {linha.acao_esperada === "nenhuma" ? (
          <span className="text-muted">nenhuma</span>
        ) : (
          acao(linha.acao_esperada).rotulo
        )}
      </td>
      <td className="px-3 py-3.5">
        <Pilula tom={TOM_DO_DESFECHO[linha.desfecho_esperado] ?? "neutro"} ponto>
          {linha.desfecho_esperado}
        </Pilula>
      </td>
    </>
  );
}

function CelulasDoJuiz({ linha, aoAbrir }: { linha: LinhaDoJuiz; aoAbrir: () => void }) {
  return (
    <>
      <Principal texto={linha.mensagem} aoAbrir={aoAbrir}>
        <p className="mt-1 line-clamp-2 border-l-2 border-line pl-2.5 text-[12.5px] leading-relaxed text-muted">
          {linha.resposta}
        </p>
      </Principal>
      <td className="px-3 py-3.5">
        <Pilula tom={linha.aprovada ? "sucesso" : "perigo"} ponto>
          {linha.aprovada ? "Aprovada" : "Reprovada"}
        </Pilula>
      </td>
      <td className="hidden px-3 py-3.5 sm:table-cell">
        <Etiqueta>{linha.conjunto}</Etiqueta>
      </td>
    </>
  );
}
