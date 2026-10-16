// Cliente HTTP fino da API do Suporte Ampère e os tipos do contrato.
// Nenhuma lógica de domínio: cada função chama uma rota e devolve o que a API respondeu.
// Tudo passa pelo BFF do próprio frontend (`/api`, mesma origem): o cookie da sessão vai
// sozinho, e o BFF o troca pelo token que a api espera. Qualquer 401 leva a /entrar.

import { irParaEntrada } from "./acesso";

const BASE = "/api";

// ---------- Vocabulário do contrato ----------

export type StatusDaConversa = "aberta" | "aprovacao_pendente" | "escalada" | "resolvida";
export type Papel = "cliente" | "assistente";
export type Linha = "notebooks" | "celulares" | "acessorios";
export type StatusDoPedido =
  | "entregue"
  | "em_transporte"
  | "aguardando_pagamento"
  | "devolvido"
  | "cancelado";
export type NomeDaAcao =
  | "consultar_pedido"
  | "consultar_base_de_conhecimento"
  | "emitir_reembolso"
  | "abrir_ticket";
export type NoDoGrafo =
  | "carregar_memoria"
  | "guardrail_entrada"
  | "roteador"
  | "recuperar_contexto"
  | "gerar_resposta"
  | "agente"
  | "guardrail_saida"
  | "escalar"
  | "salvar_memoria";
export type MotivoDoGate = "valor_acima_do_limite" | "reembolso_recente" | "gate";
export type Desfecho = "Resolvida" | "Escalada";
export type Categoria =
  | "troca"
  | "devolucao"
  | "frete"
  | "garantia"
  | "pagamento"
  | "cadastro"
  | "reembolso"
  | "outro";
export type Prioridade = "baixa" | "media" | "alta";

// ---------- Recursos ----------

export type Cliente = { id: string; nome: string; email: string };

export type Pedido = {
  id: string;
  cliente_id: string;
  produto: string;
  linha: Linha;
  valor: number;
  status: StatusDoPedido;
  data: string;
};

export type Conversa = {
  id: string;
  cliente_id: string;
  titulo: string | null;
  status: StatusDaConversa;
  criada_em: string;
  atualizada_em: string;
};

export type Mensagem = {
  id: string;
  conversa_id: string;
  papel: Papel;
  conteudo: string;
  message_id: string | null;
  criada_em: string;
};

export type Aprovacao = {
  id: string;
  conversa_id: string;
  cliente_id: string;
  pedido_id: string;
  valor: number;
  probabilidade: number;
  motivo_do_gate: MotivoDoGate | null;
  resumo: string;
  status: string;
  criada_em: string;
};

export type Ticket = {
  id: string;
  conversa_id: string;
  cliente_id: string;
  resumo: string;
  categoria: Categoria;
  prioridade: Prioridade;
  criado_em: string;
};

export type ConversaDoTicket = { ticket: Ticket; mensagens: Mensagem[] };
export type MemoriaProcedural = { texto: string };
export type MensagemEnfileirada = { enfileirada: boolean; conteudo: string };
export type Decisao = { job_id: string | number };

// ---------- Transporte ----------

export class ErroDaApi extends Error {
  constructor(
    readonly status: number,
    mensagem: string,
    /** O corpo JSON da resposta de erro, quando houver (o 409 da amostra traz o id dela). */
    readonly corpo: unknown = null,
  ) {
    super(mensagem);
    this.name = "ErroDaApi";
  }
}

/** A api recusou a sessão: quem chamou não precisa mostrar erro, a tela de entrada já vem. */
export const sessaoRecusada = (erro: unknown): boolean => erro instanceof ErroDaApi && erro.status === 401;

export function mensagemDeErro(erro: unknown): string {
  if (erro instanceof ErroDaApi) return erro.message;
  if (erro instanceof TypeError) return "Não foi possível falar com a API. Ela está no ar?";
  return erro instanceof Error ? erro.message : String(erro);
}

type Opcoes = { metodo?: "GET" | "POST" | "PUT"; cabecalhos?: Record<string, string>; corpo?: unknown };

async function requisitar<T>(caminho: string, { metodo = "GET", cabecalhos, corpo }: Opcoes = {}): Promise<T> {
  const resposta = await fetch(`${BASE}${caminho}`, {
    method: metodo,
    headers: {
      Accept: "application/json",
      ...(corpo === undefined ? {} : { "Content-Type": "application/json" }),
      ...cabecalhos,
    },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
    cache: "no-store",
  });

  if (!resposta.ok) {
    if (resposta.status === 401) irParaEntrada();
    let detalhe = resposta.statusText;
    let corpo: unknown = null;
    try {
      corpo = await resposta.json();
      const json = corpo as { detail?: unknown } | null;
      detalhe = typeof json?.detail === "string" ? json.detail : JSON.stringify(corpo);
    } catch {
      // corpo sem JSON: fica o statusText
    }
    throw new ErroDaApi(resposta.status, detalhe || `Erro ${resposta.status}`, corpo);
  }

  return resposta.status === 204 ? (undefined as T) : ((await resposta.json()) as T);
}

const doCliente = (clienteId: string) => ({ "X-Cliente-Id": clienteId });
const segmento = encodeURIComponent;

// ---------- Sessão ----------

export type Sessao = { email: string; expira_em: string };

/** Confere a sessão; um 401 aqui leva a /entrar, como em qualquer outra rota. */
export const lerSessao = () => requisitar<Sessao>("/acesso/eu");

// ---------- Rotas do Cliente ----------

export const listarClientes = () => requisitar<Cliente[]>("/clientes");

export const listarPedidos = (clienteId: string) =>
  requisitar<Pedido[]>("/pedidos", { cabecalhos: doCliente(clienteId) });

export const listarConversas = (clienteId: string) =>
  requisitar<Conversa[]>("/conversas", { cabecalhos: doCliente(clienteId) });

export const criarConversa = (clienteId: string) =>
  requisitar<{ id: string }>("/conversas", { metodo: "POST", cabecalhos: doCliente(clienteId), corpo: {} });

export const listarMensagens = (clienteId: string, conversaId: string) =>
  requisitar<Mensagem[]>(`/conversas/${segmento(conversaId)}/mensagens`, {
    cabecalhos: doCliente(clienteId),
  });

export const enviarMensagem = (
  clienteId: string,
  conversaId: string,
  corpo: { message_id: string; conteudo: string },
) =>
  requisitar<MensagemEnfileirada>(`/conversas/${segmento(conversaId)}/mensagens`, {
    metodo: "POST",
    cabecalhos: doCliente(clienteId),
    corpo,
  });

export const urlDoStream = (clienteId: string, conversaId: string) =>
  `${BASE}/conversas/${segmento(conversaId)}/stream?cliente_id=${segmento(clienteId)}`;

// ---------- Rotas do Atendente ----------

export const listarAprovacoes = () => requisitar<Aprovacao[]>("/atendente/aprovacoes");

export const aprovarReembolso = (aprovacaoId: string) =>
  requisitar<Decisao>(`/atendente/aprovacoes/${segmento(aprovacaoId)}/aprovar`, { metodo: "POST" });

export const rejeitarReembolso = (aprovacaoId: string, motivo?: string) =>
  requisitar<Decisao>(`/atendente/aprovacoes/${segmento(aprovacaoId)}/rejeitar`, {
    metodo: "POST",
    corpo: motivo ? { motivo } : {},
  });

export const listarTickets = () => requisitar<Ticket[]>("/atendente/tickets");

export const lerConversaDoTicket = (ticketId: string) =>
  requisitar<ConversaDoTicket>(`/atendente/tickets/${segmento(ticketId)}/conversa`);

const rotaDaMemoria = (clienteId: string) =>
  `/atendente/clientes/${segmento(clienteId)}/memoria-procedural`;

export const lerMemoriaProcedural = (clienteId: string) =>
  requisitar<MemoriaProcedural>(rotaDaMemoria(clienteId));

export const salvarMemoriaProcedural = (clienteId: string, texto: string) =>
  requisitar<MemoriaProcedural>(rotaDaMemoria(clienteId), { metodo: "PUT", corpo: { texto } });

// ---------- Avaliação ----------

export type NomeDoEval = "rag" | "agente" | "juiz";
export type ModoDaExecucao = "completa" | "amostra";
export type StatusDaExecucao = "pendente" | "rodando" | "concluida" | "erro";
export type Veredito = { aprovada: boolean; critica: string };
export type Sorteado = { id: string; texto: string; grupo: string };

export type ContextoDaExecucao = {
  modelos_falsos?: boolean;
  gerador?: string;
  juiz?: string;
  trabalhador?: string;
  prompts?: Record<string, string>;
  n?: number;
  variante?: string;
  seed?: number;
  sorteados?: Sorteado[];
};

/** O que todo caso tem, de qualquer eval. Um caso que falhou na amostra tem só isto. */
export type CasoBase = {
  id: string;
  texto: string;
  grupo: string;
  duracao_s: number;
  erro: string | null;
};

export type CasoRag = CasoBase & {
  pergunta: string;
  origem: string;
  documento_esperado: string;
  recuperados: string[];
  posicao: number | null;
  filtro: Record<string, string> | null;
  resposta: string | null;
  fidelidade: Veredito | null;
  relevancia: Veredito | null;
};

export type Tripla<T> = { intencao: T; acao: T; desfecho: T };

export type CasoAgente = CasoBase & {
  mensagem: string;
  esperado: Tripla<string | null>;
  obtido: Tripla<string>;
  ok: Tripla<boolean>;
  bloqueado: boolean;
  caminho: string[];
  resposta: string;
  juiz: Veredito | null;
};

export type CasoJuiz = CasoBase & {
  conjunto: "dev" | "teste";
  mensagem: string;
  resposta: string;
  humano: Veredito;
  juiz: Veredito;
  concorda: boolean;
};

export type Caso = CasoRag | CasoAgente | CasoJuiz | CasoBase;

export type VarianteRag = {
  nome: string;
  embedder: string;
  chunker: string;
  reranker: string;
  self_querying: boolean;
  recall_at_5: number;
  mrr: number;
};

export type ResumoRag = {
  variante_no_ar: string;
  recall_at_5: number | null;
  mrr: number | null;
  fidelidade: number | null;
  relevancia: number | null;
  n: number;
  variantes: VarianteRag[];
};

export type ResumoAgente = {
  n: number;
  erros: number;
  intencao: number;
  acao: number;
  desfecho: number;
  tudo: number;
  juiz_aprovadas: number;
  julgados: number;
};

export type Matriz = { vp: number; fn: number; vn: number; fp: number };
export type AvaliacaoDoConjunto = { matriz: Matriz; tpr: number; tnr: number; concordancia: number };

export type ResumoCalibracao = {
  tamanhos: { treino: number; dev: number; teste: number };
  dev: AvaliacaoDoConjunto;
  teste: AvaliacaoDoConjunto;
  taxa_observada: number;
  taxa_corrigida: number;
  intervalo: [number, number];
};

export type ResumoAmostraJuiz = { n: number; concordaram: number; erros: number };

export type Execucao = {
  id: string;
  eval: NomeDoEval;
  modo: ModoDaExecucao;
  status: StatusDaExecucao;
  contexto: ContextoDaExecucao;
  resumo: unknown;
  erro: string | null;
  criada_em: string;
  iniciada_em: string | null;
  concluida_em: string | null;
  /** Só vem em `lerExecucao` e na foto do stream; as listas não trazem os casos. */
  casos?: Caso[];
};

export type AmostraDisparada = { execucao_id: string };
export type AmostraOcupada = { detail: string; execucao_id: string | null; eval: NomeDoEval | null };

/** Até 100: cada amostra entra na lista, e a completa não pode sumir no meio da aula. */
export const listarExecucoes = (nome: NomeDoEval) =>
  requisitar<Execucao[]>(`/avaliacao/${nome}/execucoes?limite=100`);

export const lerExecucao = (execucaoId: string) =>
  requisitar<Execucao>(`/avaliacao/execucoes/${segmento(execucaoId)}`);

export const lerAmostraEmAndamento = () => requisitar<Execucao | null>("/avaliacao/amostra");

export const rodarAmostra = (nome: NomeDoEval) =>
  requisitar<AmostraDisparada>(`/avaliacao/${nome}/amostra`, { metodo: "POST" });

export const urlDoStreamDaExecucao = (execucaoId: string) =>
  `${BASE}/avaliacao/execucoes/${segmento(execucaoId)}/stream`;
