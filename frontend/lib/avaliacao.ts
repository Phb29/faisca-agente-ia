// Textos e contas da Tela de Avaliação. Os textos são o que se lê no telão: uma pergunta
// grande e uma frase simples do que a métrica mede, sem jargão.

import type { CasoBase, Execucao, NomeDoEval } from "./api";
import { formatarMomento } from "./formatos";

export const ABAS: NomeDoEval[] = ["rag", "agente", "juiz"];
export const TAMANHO_DA_AMOSTRA = 3;

type Textos = {
  rotulo: string;
  sobretitulo: string;
  pergunta: string;
  unidade: string;
  botao: string;
  comando: string;
};

export const TEXTOS: Record<NomeDoEval, Textos> = {
  rag: {
    rotulo: "Busca",
    sobretitulo: "Avaliação · RAG",
    pergunta: "A busca encontra o documento certo?",
    unidade: "perguntas",
    botao: "Rodar 3 ao vivo",
    comando: "railway ssh --service worker -- ampere-evals rag",
  },
  agente: {
    rotulo: "Agente",
    sobretitulo: "Avaliação · Agente",
    pergunta: "O agente toma o caminho certo?",
    unidade: "cenários",
    botao: "Rodar 3 ao vivo",
    comando: "railway ssh --service worker -- ampere-evals agente",
  },
  juiz: {
    rotulo: "Juiz",
    sobretitulo: "Avaliação · Calibração do juiz",
    pergunta: "Dá para confiar no juiz?",
    unidade: "respostas",
    botao: "Julgar 3 ao vivo",
    comando: "railway ssh --service worker -- ampere-evals calibracao",
  },
};

/** A frase do que a métrica mede, com o tamanho da rodada escolhida. */
export function fraseDaAba(nome: NomeDoEval, execucao: Execucao | null): string {
  const n = execucao?.contexto.n ?? "…";
  const amostra = execucao?.modo === "amostra";
  if (nome === "rag") {
    return amostra
      ? "Amostra ao vivo: 3 perguntas sorteadas, na variante que está no ar, com a resposta julgada."
      : `Para cada uma das ${n} perguntas, olhamos se o documento que tem a resposta aparece entre os 5 primeiros e em que posição ele chega.`;
  }
  if (nome === "agente") {
    const quantos = amostra ? "Amostra ao vivo: 3" : String(n);
    return `${quantos} cenários de um turno no grafo real. O código confere a intenção, a Ação e o desfecho. O juiz lê a resposta final.`;
  }
  const resumo = execucao?.resumo as { tamanhos?: { treino: number; dev: number; teste: number } } | null;
  const tamanhos = resumo?.tamanhos;
  if (amostra || !tamanhos) {
    return "Amostra ao vivo: 3 respostas do conjunto de teste, julgadas com os exemplos do treino no prompt.";
  }
  return `${n} respostas rotuladas por humano. ${tamanhos.treino} viram exemplos do prompt, ${tamanhos.dev} medem o juiz e ${tamanhos.teste} recebem a correção.`;
}

export function abaValida(valor: string | null): NomeDoEval {
  return ABAS.find((aba) => aba === valor) ?? "rag";
}

export const temErro = (caso: CasoBase): boolean => Boolean(caso.erro);

export const decimal = (valor: number | null | undefined): string =>
  valor == null
    ? "—"
    : valor.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const porcento = (valor: number | null | undefined): string =>
  valor == null ? "—" : String(Math.round(valor * 100));

export const segundos = (valor: number): string =>
  `${valor.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} s`;

export function relogio(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutos = String(Math.floor(total / 60)).padStart(2, "0");
  return `${minutos}:${String(total % 60).padStart(2, "0")}`;
}

export function fraseDoMrr(mrr: number | null | undefined): string {
  if (mrr == null) return "sem dados";
  if (mrr >= 0.9) return "o certo quase sempre vem em 1º";
  if (mrr >= 0.6) return "o certo costuma vir em 1º ou 2º";
  if (mrr >= 0.4) return "o certo costuma vir até o 3º";
  return "o certo costuma vir tarde, ou nem vir";
}

const GRUPOS: Record<string, string> = {
  duvida: "Dúvida",
  transacao: "Transação",
  quer_humano: "Pedido de humano",
  bloqueio: "Bloqueio",
  adversarial: "adversarial",
  manual: "manual",
  aprovada: "humano aprovou",
  reprovada: "humano reprovou",
};

export const rotuloDoGrupo = (grupo: string): string => GRUPOS[grupo] ?? grupo;

const FASES: Record<string, string> = {
  busca: "busca",
  resposta: "resposta",
  juiz: "juiz",
  carregar_memoria: "memória",
  guardrail_entrada: "guardrail",
  roteador: "roteador",
  recuperar_contexto: "busca",
  gerar_resposta: "resposta",
  agente: "agente",
  guardrail_saida: "guardrail de saída",
  escalar: "escalar",
  salvar_memoria: "salvar memória",
};

export const rotuloDaFase = (fase: string): string => FASES[fase] ?? fase.replace(/_/g, " ");

/** Uma linha para o seletor de execução: quando, que tipo e se foi em modo demonstração. */
export function descreverExecucao(execucao: Execucao): string {
  const partes = [formatarMomento(execucao.criada_em)];
  if (execucao.modo === "completa") {
    // No juiz, o `n` do contexto são as respostas rotuladas (treino + dev + teste); a rodada
    // em si julga só as 36 de dev e teste, as de treino são os exemplos do prompt.
    const unidade = execucao.eval === "juiz" ? "respostas rotuladas" : "casos";
    partes.push(`completa · ${execucao.contexto.n ?? "?"} ${unidade}`);
  } else {
    partes.push("amostra ao vivo");
  }
  if (execucao.contexto.modelos_falsos) partes.push("modo demonstração");
  if (execucao.status === "erro") partes.push("parou com erro");
  return partes.join(" · ");
}
