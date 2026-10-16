// Stream SSE de uma Conversa. O EventSource não envia headers, então o Cliente vai na
// query string; a sessão vai no cookie, que o BFF troca pelo token. A reconexão é nativa
// do navegador; ao reconectar, o servidor reenvia a última resposta gravada como
// `message_done` com `reenvio: true`.

import {
  lerSessao,
  urlDoStream,
  type Desfecho,
  type MotivoDoGate,
  type NoDoGrafo,
  type NomeDaAcao,
} from "./api";

export type EventoToken = { texto: string };
export type EventoToolCall = { nome: NomeDaAcao; args: Record<string, unknown> };
export type EventoEtapa = { no: NoDoGrafo; detalhe: string | null; alerta: boolean };
export type EventoApprovalRequired = {
  aprovacao_id: string;
  pedido_id: string;
  valor: number;
  probabilidade: number;
  resumo: string;
  motivo_do_gate: MotivoDoGate | null;
};
export type EventoMessageDone = {
  mensagem_id: string;
  conteudo: string;
  desfecho?: Desfecho | null;
  reenvio?: boolean;
};
export type EventoError = { mensagem: string };

export type EventoDoStream =
  | { tipo: "token"; dados: EventoToken }
  | { tipo: "tool_call"; dados: EventoToolCall }
  | { tipo: "etapa"; dados: EventoEtapa }
  | { tipo: "approval_required"; dados: EventoApprovalRequired }
  | { tipo: "message_done"; dados: EventoMessageDone }
  | { tipo: "error"; dados: EventoError };

export type Conexao = "conectando" | "aberta" | "reconectando" | "fechada";

type Ouvintes = {
  aoEvento: (evento: EventoDoStream) => void;
  aoMudarConexao: (conexao: Conexao) => void;
};

const TIPOS_COM_DADOS = ["token", "tool_call", "etapa", "approval_required", "message_done"] as const;

function lerJson<T>(evento: Event): T | null {
  const dados = (evento as MessageEvent<string>).data;
  if (!dados) return null;
  try {
    return JSON.parse(dados) as T;
  } catch {
    return null;
  }
}

/** Abre o stream da Conversa e devolve a função que o fecha. */
export function conectarStream(
  clienteId: string,
  conversaId: string,
  { aoEvento, aoMudarConexao }: Ouvintes,
): () => void {
  const fonte = new EventSource(urlDoStream(clienteId, conversaId));
  aoMudarConexao("conectando");

  fonte.addEventListener("open", () => aoMudarConexao("aberta"));

  for (const tipo of TIPOS_COM_DADOS) {
    fonte.addEventListener(tipo, (evento) => {
      const dados = lerJson(evento);
      if (dados) aoEvento({ tipo, dados } as EventoDoStream);
    });
  }

  // O nome `error` serve a dois propósitos: o evento do servidor (com `mensagem`) e a
  // falha de rede do próprio EventSource (sem dados), em que o navegador reconecta sozinho.
  fonte.addEventListener("error", (evento) => {
    const dados = lerJson<EventoError>(evento);
    if (dados?.mensagem) {
      aoEvento({ tipo: "error", dados });
      return;
    }
    const desistiu = fonte.readyState === EventSource.CLOSED;
    aoMudarConexao(desistiu ? "fechada" : "reconectando");
    // O navegador desiste quando a resposta não é 200, mas não diz o status. Se foi a sessão
    // vencida, a conferência dá 401 e o `requisitar` leva à tela de entrada.
    if (desistiu) lerSessao().catch(() => undefined);
  });

  return () => fonte.close();
}
