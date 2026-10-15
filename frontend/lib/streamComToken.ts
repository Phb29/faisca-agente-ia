// Stream SSE lido com fetch, para mandar o token do Atendente no cabeçalho: o EventSource
// não manda cabeçalho, e token na URL acabaria nos logs. Reconecta sozinho, com espera
// crescente, enquanto quem ouve não disser que acabou; ao reconectar, a API manda de novo a
// foto da execução, então nada se perde.

import { ErroDaApi } from "./api";

export type EventoBruto = { tipo: string; dados: unknown };
export type EstadoDaConexao = "conectando" | "aberta" | "reconectando" | "fechada";

type Opcoes = {
  url: string;
  cabecalhos: Record<string, string>;
  /** Devolve true quando o stream acabou de vez: não reconecta mais. */
  aoEvento: (evento: EventoBruto) => boolean;
  aoMudarConexao: (estado: EstadoDaConexao) => void;
  /** Resposta que não adianta repetir (401 ou 404). */
  aoFalhar: (erro: ErroDaApi) => void;
};

const ESPERA_MAXIMA_MS = 10_000;
// O servidor manda um ping a cada 15 s: 45 s de silêncio é conexão meio morta (Wi-Fi do
// evento), e o leitor desiste para reconectar.
const SILENCIO_MAXIMO_MS = 45_000;

const esperar = (ms: number) => new Promise((resolver) => setTimeout(resolver, ms));

/** Abre o stream e devolve a função que o fecha. */
export function abrirStreamComToken({
  url,
  cabecalhos,
  aoEvento,
  aoMudarConexao,
  aoFalhar,
}: Opcoes): () => void {
  let encerrado = false;
  let controle: AbortController | null = null;

  async function rodar() {
    let espera = 0;
    while (!encerrado) {
      if (espera > 0) {
        aoMudarConexao("reconectando");
        await esperar(espera);
        if (encerrado) break;
      } else {
        aoMudarConexao("conectando");
      }
      espera = Math.min(Math.max(espera * 2, 1000), ESPERA_MAXIMA_MS);
      controle = new AbortController();
      try {
        const resposta = await fetch(url, {
          headers: { Accept: "text/event-stream", ...cabecalhos },
          signal: controle.signal,
          cache: "no-store",
        });
        if (resposta.status === 401 || resposta.status === 404) {
          encerrado = true;
          const mensagem = resposta.status === 401 ? "Token recusado." : "Amostra não encontrada.";
          aoFalhar(new ErroDaApi(resposta.status, mensagem));
          break;
        }
        if (!resposta.ok || !resposta.body) continue;
        aoMudarConexao("aberta");
        espera = 1000;
        if (await lerEventos(resposta.body, aoEvento)) encerrado = true;
      } catch {
        // a rede caiu ou o stream foi abortado: o laço decide se tenta de novo
      }
    }
    aoMudarConexao("fechada");
  }

  void rodar();
  return () => {
    encerrado = true;
    controle?.abort();
  };
}

/** Lê o stream até o fim e devolve true se `aoEvento` disse que acabou. */
async function lerEventos(
  corpo: ReadableStream<Uint8Array>,
  aoEvento: (evento: EventoBruto) => boolean,
): Promise<boolean> {
  const leitor = corpo.getReader();
  const decodificador = new TextDecoder();
  let resto = "";
  let tipo = "message";
  let dados: string[] = [];
  try {
    for (;;) {
      // O relógio é desligado quando a leitura chega, para a promessa não rejeitar à toa depois.
      let relogio: ReturnType<typeof setTimeout> | undefined;
      const silencio = new Promise<never>((_, rejeitar) => {
        relogio = setTimeout(() => rejeitar(new Error("stream em silêncio")), SILENCIO_MAXIMO_MS);
      });
      const { value, done } = await Promise.race([leitor.read(), silencio]).finally(() =>
        clearTimeout(relogio),
      );
      if (done) return false;
      resto += decodificador.decode(value, { stream: true });
      let quebra = resto.indexOf("\n");
      while (quebra >= 0) {
        const linha = resto.slice(0, quebra).replace(/\r$/, "");
        resto = resto.slice(quebra + 1);
        if (linha === "") {
          if (dados.length > 0 && aoEvento({ tipo, dados: JSON.parse(dados.join("\n")) })) {
            return true;
          }
          tipo = "message";
          dados = [];
        } else if (linha.startsWith("event:")) {
          tipo = linha.slice(6).trim();
        } else if (linha.startsWith("data:")) {
          dados.push(linha.slice(5).trimStart());
        }
        quebra = resto.indexOf("\n");
      }
    }
  } finally {
    leitor.cancel().catch(() => undefined);
  }
}
