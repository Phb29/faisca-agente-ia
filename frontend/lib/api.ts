// Cliente HTTP fino da API do Suporte Ampère e os tipos do contrato.
// Nenhuma lógica de domínio: cada função chama uma rota e devolve o que a API respondeu.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  ) {
    super(mensagem);
    this.name = "ErroDaApi";
  }
}

export function mensagemDeErro(erro: unknown): string {
  if (erro instanceof ErroDaApi) return erro.message;
  if (erro instanceof TypeError) return "Não foi possível falar com a API. Ela está no ar?";
  return erro instanceof Error ? erro.message : String(erro);
}

type Opcoes = { metodo?: "GET" | "POST" | "PUT"; cabecalhos?: Record<string, string>; corpo?: unknown };

async function requisitar<T>(caminho: string, { metodo = "GET", cabecalhos, corpo }: Opcoes = {}): Promise<T> {
  const resposta = await fetch(`${API_URL}${caminho}`, {
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
    let detalhe = resposta.statusText;
    try {
      const json = await resposta.json();
      detalhe = typeof json?.detail === "string" ? json.detail : JSON.stringify(json);
    } catch {
      // corpo sem JSON: fica o statusText
    }
    throw new ErroDaApi(resposta.status, detalhe || `Erro ${resposta.status}`);
  }

  return resposta.status === 204 ? (undefined as T) : ((await resposta.json()) as T);
}

const doCliente = (clienteId: string) => ({ "X-Cliente-Id": clienteId });
const doAtendente = (token: string) => ({ "X-Atendente-Token": token });
const segmento = encodeURIComponent;

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
  `${API_URL}/conversas/${segmento(conversaId)}/stream?cliente_id=${segmento(clienteId)}`;

// ---------- Rotas do Atendente ----------

export const listarAprovacoes = (token: string) =>
  requisitar<Aprovacao[]>("/atendente/aprovacoes", { cabecalhos: doAtendente(token) });

export const aprovarReembolso = (token: string, aprovacaoId: string) =>
  requisitar<Decisao>(`/atendente/aprovacoes/${segmento(aprovacaoId)}/aprovar`, {
    metodo: "POST",
    cabecalhos: doAtendente(token),
  });

export const rejeitarReembolso = (token: string, aprovacaoId: string, motivo?: string) =>
  requisitar<Decisao>(`/atendente/aprovacoes/${segmento(aprovacaoId)}/rejeitar`, {
    metodo: "POST",
    cabecalhos: doAtendente(token),
    corpo: motivo ? { motivo } : {},
  });

export const listarTickets = (token: string) =>
  requisitar<Ticket[]>("/atendente/tickets", { cabecalhos: doAtendente(token) });

export const lerConversaDoTicket = (token: string, ticketId: string) =>
  requisitar<ConversaDoTicket>(`/atendente/tickets/${segmento(ticketId)}/conversa`, {
    cabecalhos: doAtendente(token),
  });

const rotaDaMemoria = (clienteId: string) =>
  `/atendente/clientes/${segmento(clienteId)}/memoria-procedural`;

export const lerMemoriaProcedural = (token: string, clienteId: string) =>
  requisitar<MemoriaProcedural>(rotaDaMemoria(clienteId), { cabecalhos: doAtendente(token) });

export const salvarMemoriaProcedural = (token: string, clienteId: string, texto: string) =>
  requisitar<MemoriaProcedural>(rotaDaMemoria(clienteId), {
    metodo: "PUT",
    cabecalhos: doAtendente(token),
    corpo: { texto },
  });
