// Conexão SSE com o stream de uma Conversa.
// O EventSource não aceita headers customizados, então o id do Cliente vai
// na query string (?cliente_id=), alternativa aceita pela rota de stream.
// A reconexão automática é nativa do EventSource; ao reconectar, o servidor
// reenvia a última mensagem do assistente como `message_done` com `reenvio: true`.

import { API_URL } from "./api";

export type NomeDaAcao =
  | "consultar_pedido"
  | "consultar_base_de_conhecimento"
  | "emitir_reembolso"
  | "abrir_ticket";

export type EventoToken = { texto: string };
export type EventoToolCall = { nome: NomeDaAcao; args: Record<string, unknown> };
export type EventoApprovalRequired = {
  aprovacao_id: string;
  pedido_id: string;
  valor: number;
  probabilidade: number;
  resumo: string;
};
export type EventoMessageDone = {
  mensagem_id: string;
  conteudo: string;
  reenvio?: boolean;
};
export type EventoError = { mensagem: string };

export type HandlersDoStream = {
  onToken?: (evento: EventoToken) => void;
  onToolCall?: (evento: EventoToolCall) => void;
  onApprovalRequired?: (evento: EventoApprovalRequired) => void;
  onMessageDone?: (evento: EventoMessageDone) => void;
  onError?: (evento: EventoError) => void;
  onConexao?: (estado: "aberta" | "reconectando") => void;
};

function lerJson<T>(evento: Event): T | null {
  const dados = (evento as MessageEvent<string>).data;
  if (!dados) return null;
  try {
    return JSON.parse(dados) as T;
  } catch {
    return null;
  }
}

/**
 * Abre o stream da Conversa e devolve uma função que fecha a conexão.
 */
export function conectarStream(
  conversaId: string,
  clienteId: string,
  handlers: HandlersDoStream,
): () => void {
  const url = `${API_URL}/conversas/${encodeURIComponent(conversaId)}/stream?cliente_id=${encodeURIComponent(clienteId)}`;
  const fonte = new EventSource(url);

  fonte.addEventListener("open", () => handlers.onConexao?.("aberta"));

  fonte.addEventListener("token", (evento) => {
    const dados = lerJson<EventoToken>(evento);
    if (dados) handlers.onToken?.(dados);
  });

  fonte.addEventListener("tool_call", (evento) => {
    const dados = lerJson<EventoToolCall>(evento);
    if (dados) handlers.onToolCall?.(dados);
  });

  fonte.addEventListener("approval_required", (evento) => {
    const dados = lerJson<EventoApprovalRequired>(evento);
    if (dados) handlers.onApprovalRequired?.(dados);
  });

  fonte.addEventListener("message_done", (evento) => {
    const dados = lerJson<EventoMessageDone>(evento);
    if (dados) handlers.onMessageDone?.(dados);
  });

  // Evento nomeado `error` vindo do servidor (traz {mensagem}).
  // O mesmo nome é usado pelo EventSource para falhas de rede, que não têm `data`:
  // nesse caso o navegador reconecta sozinho e só avisamos o estado.
  fonte.addEventListener("error", (evento) => {
    const dados = lerJson<EventoError>(evento);
    if (dados?.mensagem) {
      handlers.onError?.(dados);
      return;
    }
    if (fonte.readyState === EventSource.CONNECTING) {
      handlers.onConexao?.("reconectando");
    }
  });

  return () => fonte.close();
}
