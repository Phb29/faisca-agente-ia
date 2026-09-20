// Cliente HTTP fino da API do Suporte Ampère.
// Nenhuma lógica de domínio: cada função chama uma rota e devolve o que a API respondeu.

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type StatusDaConversa =
  | "aberta"
  | "aprovacao_pendente"
  | "escalada"
  | "resolvida";

export type Cliente = { id: string; nome: string; email: string };

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
  papel: "cliente" | "assistente";
  conteudo: string;
  criada_em: string;
};

export type Aprovacao = {
  id: string;
  conversa_id: string;
  cliente_id: string;
  pedido_id: string;
  valor: number;
  probabilidade: number;
  resumo: string;
  status: string;
  criada_em: string;
};

export type Ticket = {
  id: string;
  conversa_id: string;
  cliente_id: string;
  resumo: string;
  categoria: string;
  prioridade: string;
  criado_em: string;
};

export type ConversaDoTicket = { ticket: Ticket; mensagens: Mensagem[] };

export type MemoriaProcedural = { texto: string };

export class ErroDaApi extends Error {
  status: number;

  constructor(status: number, mensagem: string) {
    super(mensagem);
    this.name = "ErroDaApi";
    this.status = status;
  }
}

async function requisitar<T>(
  caminho: string,
  init: RequestInit & { headers?: Record<string, string> } = {},
): Promise<T> {
  const resposta = await fetch(`${API_URL}${caminho}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!resposta.ok) {
    let detalhe = resposta.statusText;
    try {
      const corpo = await resposta.json();
      detalhe = corpo?.detail ?? corpo?.mensagem ?? JSON.stringify(corpo);
    } catch {
      // corpo não é JSON; fica o statusText
    }
    throw new ErroDaApi(resposta.status, `${resposta.status}: ${detalhe}`);
  }

  if (resposta.status === 204) return undefined as T;
  return (await resposta.json()) as T;
}

const comCliente = (clienteId: string) => ({ "X-Cliente-Id": clienteId });
const comAtendente = (token: string) => ({ "X-Atendente-Token": token });

// ---------- Rotas públicas ----------

export function listarClientes(): Promise<Cliente[]> {
  return requisitar<Cliente[]>("/clientes");
}

// ---------- Rotas do Cliente ----------

export function criarConversa(clienteId: string): Promise<{ id: string }> {
  return requisitar<{ id: string }>("/conversas", {
    method: "POST",
    headers: comCliente(clienteId),
  });
}

export function listarConversas(clienteId: string): Promise<Conversa[]> {
  return requisitar<Conversa[]>("/conversas", {
    headers: comCliente(clienteId),
  });
}

export function listarMensagens(
  clienteId: string,
  conversaId: string,
): Promise<Mensagem[]> {
  return requisitar<Mensagem[]>(
    `/conversas/${encodeURIComponent(conversaId)}/mensagens`,
    { headers: comCliente(clienteId) },
  );
}

export function enviarMensagem(
  clienteId: string,
  conversaId: string,
  corpo: { message_id: string; conteudo: string },
): Promise<{ enfileirada: boolean }> {
  return requisitar<{ enfileirada: boolean }>(
    `/conversas/${encodeURIComponent(conversaId)}/mensagens`,
    {
      method: "POST",
      headers: comCliente(clienteId),
      body: JSON.stringify(corpo),
    },
  );
}

// ---------- Rotas do Atendente ----------

export function listarAprovacoes(token: string): Promise<Aprovacao[]> {
  return requisitar<Aprovacao[]>("/atendente/aprovacoes", {
    headers: comAtendente(token),
  });
}

export function aprovarReembolso(
  token: string,
  aprovacaoId: string,
): Promise<{ job_id: string }> {
  return requisitar<{ job_id: string }>(
    `/atendente/aprovacoes/${encodeURIComponent(aprovacaoId)}/aprovar`,
    { method: "POST", headers: comAtendente(token) },
  );
}

export function rejeitarReembolso(
  token: string,
  aprovacaoId: string,
  motivo?: string,
): Promise<{ job_id: string }> {
  return requisitar<{ job_id: string }>(
    `/atendente/aprovacoes/${encodeURIComponent(aprovacaoId)}/rejeitar`,
    {
      method: "POST",
      headers: comAtendente(token),
      body: JSON.stringify(motivo ? { motivo } : {}),
    },
  );
}

export function listarTickets(token: string): Promise<Ticket[]> {
  return requisitar<Ticket[]>("/atendente/tickets", {
    headers: comAtendente(token),
  });
}

export function lerConversaDoTicket(
  token: string,
  ticketId: string,
): Promise<ConversaDoTicket> {
  return requisitar<ConversaDoTicket>(
    `/atendente/tickets/${encodeURIComponent(ticketId)}/conversa`,
    { headers: comAtendente(token) },
  );
}

export function lerMemoriaProcedural(
  token: string,
  clienteId: string,
): Promise<MemoriaProcedural> {
  return requisitar<MemoriaProcedural>(
    `/atendente/clientes/${encodeURIComponent(clienteId)}/memoria-procedural`,
    { headers: comAtendente(token) },
  );
}

export function salvarMemoriaProcedural(
  token: string,
  clienteId: string,
  texto: string,
): Promise<MemoriaProcedural> {
  return requisitar<MemoriaProcedural>(
    `/atendente/clientes/${encodeURIComponent(clienteId)}/memoria-procedural`,
    {
      method: "PUT",
      headers: comAtendente(token),
      body: JSON.stringify({ texto }),
    },
  );
}
