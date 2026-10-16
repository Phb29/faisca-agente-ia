"use client";

import { X } from "lucide-react";
import type { ConjuntoDoJuiz, LinhaDaBusca, LinhaDoAgente, LinhaDoJuiz, LinhaDosDados } from "@/lib/api";
import { rotuloDoGrupo } from "@/lib/avaliacao";
import { acao } from "@/lib/rotulos";
import { BotaoDeIcone } from "@/components/ui/Botao";
import { Gaveta } from "@/components/ui/Gaveta";
import { Pilula } from "@/components/ui/Pilula";
import { Balao, Bloco, Etiqueta } from "./GavetaDoCaso";
import { Voz } from "./Quadrinho";
import { TOM_DO_DESFECHO } from "./TabelaDeDados";

type Props = { linha: LinhaDosDados | null; aoFechar: () => void };

const PAPEL_DO_CONJUNTO: Record<ConjuntoDoJuiz, string> = {
  treino: "Treino: entra como exemplo no prompt do juiz. Por isso nunca serve para medir o juiz.",
  dev: "Dev: o juiz julga esta resposta e o voto dele é comparado com o do humano. É daqui que saem o TPR e o TNR.",
  teste: "Teste: recebe a correção de Rogan-Gladen no fim. A amostra ao vivo da aba Juiz sorteia daqui.",
};

/** O detalhe de uma linha de um golden: o texto inteiro e o que o eval confere com ela. */
export function GavetaDoDado({ linha, aoFechar }: Props) {
  return (
    <Gaveta aberta={linha !== null} aoFechar={aoFechar} rotulo="Linha do golden" largura="max-w-xl">
      {linha && (
        <>
          <div className="flex items-start gap-3 border-b border-line px-5 pt-5 pb-4">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap gap-1.5">
                <Etiqueta>{linha.id}</Etiqueta>
                <Etiqueta>{rotuloDoGrupo(linha.grupo)}</Etiqueta>
                {"conjunto" in linha && <Etiqueta>{linha.conjunto}</Etiqueta>}
              </div>
              <h2 className="mt-2 text-[17px] leading-snug font-semibold tracking-[-0.015em]">
                “{"pergunta" in linha ? linha.pergunta : linha.mensagem}”
              </h2>
            </div>
            <BotaoDeIcone icone={X} rotulo="Fechar" onClick={aoFechar} />
          </div>
          <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
            {"pergunta" in linha ? (
              <DaBusca linha={linha} />
            ) : "conjunto" in linha ? (
              <DoJuiz linha={linha} />
            ) : (
              <DoAgente linha={linha} />
            )}
          </div>
        </>
      )}
    </Gaveta>
  );
}

function DaBusca({ linha }: { linha: LinhaDaBusca }) {
  return (
    <>
      <Bloco titulo="Documento esperado">
        <p className="inline-block rounded-lg bg-volt/30 px-2.5 py-1.5 font-mono text-[13px] font-semibold ring-1 ring-volt-forte ring-inset">
          {linha.documento_esperado}
        </p>
        <p className="mt-2 text-[13px] leading-relaxed text-muted">
          A busca acerta quando este documento aparece entre os 5 primeiros. O Recall@5 conta se apareceu; o MRR,
          em que posição.
        </p>
      </Bloco>
      <Bloco titulo="Resposta de referência">
        <Balao>{linha.resposta_referencia}</Balao>
        <p className="mt-2 text-[13px] leading-relaxed text-muted">
          Nenhuma métrica usa esta resposta: o juiz confere a resposta gerada contra os trechos que a busca trouxe.
          Ela serve para um humano ler ao lado.
        </p>
      </Bloco>
      {linha.grupo === "adversarial" && (
        <p className="text-[13px] leading-relaxed text-muted">
          Adversarial: feita para parecer com outro documento da mesma categoria, como garantia de celular contra
          garantia de notebook.
        </p>
      )}
    </>
  );
}

function DoAgente({ linha }: { linha: LinhaDoAgente }) {
  const conferencias: [string, string][] = [
    ["Guardrail", linha.guardrail_bloqueia ? "barra a mensagem" : "deixa passar"],
    ["Intenção", linha.intencao_esperada ? rotuloDoGrupo(linha.intencao_esperada) : "nenhuma, barrada antes"],
    ["Ação", linha.acao_esperada === "nenhuma" ? "nenhuma" : acao(linha.acao_esperada).rotulo],
  ];
  return (
    <>
      <Bloco titulo="Quem pergunta">
        <p className="font-mono text-[13px] text-ink-2">
          {linha.cliente_id}
          {linha.pedido_id && ` · Pedido ${linha.pedido_id}`}
        </p>
      </Bloco>
      <Bloco titulo="Memórias pré-carregadas">
        {linha.memorias ? (
          <Balao>{linha.memorias}</Balao>
        ) : (
          <p className="text-[13px] text-muted">Nenhuma: o Cliente chega sem memória.</p>
        )}
      </Bloco>
      <Bloco titulo="O que o código confere">
        <div className="divide-y divide-line">
          {conferencias.map(([rotulo, valor]) => (
            <div key={rotulo} className="grid grid-cols-[96px_1fr] items-center gap-2 py-2 text-[13px]">
              <span className="sobretitulo">{rotulo}</span>
              <span className="text-ink-2">{valor}</span>
            </div>
          ))}
          <div className="grid grid-cols-[96px_1fr] items-center gap-2 py-2 text-[13px]">
            <span className="sobretitulo">Desfecho</span>
            <span>
              <Pilula tom={TOM_DO_DESFECHO[linha.desfecho_esperado] ?? "neutro"} ponto>
                {linha.desfecho_esperado}
              </Pilula>
            </span>
          </div>
        </div>
        <p className="mt-2 text-[13px] leading-relaxed text-muted">
          O código lê o estado final do grafo, não a frase do agente: a primeira Ação tomada e o desfecho. Um
          turno que parou no Gate conta como Aprovação Pendente.
        </p>
      </Bloco>
    </>
  );
}

function DoJuiz({ linha }: { linha: LinhaDoJuiz }) {
  return (
    <>
      <Bloco titulo="Resposta do chatbot">
        <Balao>{linha.resposta}</Balao>
      </Bloco>
      <Voz quem="Humano" veredito={{ aprovada: linha.aprovada, critica: linha.critica }} />
      <p className="text-[13px] leading-relaxed text-muted">{PAPEL_DO_CONJUNTO[linha.conjunto]}</p>
    </>
  );
}
