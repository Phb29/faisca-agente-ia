// localStorage protegido (o servidor não tem window) e observável, para o
// `useArmazenado` reagir a gravações feitas nesta aba e em outras.

export const CHAVES = {
  cliente: "ampere.cliente",
  tokenDoAtendente: "ampere.atendente.token",
  painelAberto: "ampere.chat.painel",
} as const;

const EVENTO = "ampere:armazenamento";

export function lerBruto(chave: string): string | null {
  try {
    return window.localStorage.getItem(chave);
  } catch {
    return null;
  }
}

export function gravar(chave: string, valor: unknown): void {
  try {
    window.localStorage.setItem(chave, JSON.stringify(valor));
  } catch {
    // armazenamento indisponível (modo privado, cota): segue sem persistir
  }
  window.dispatchEvent(new Event(EVENTO));
}

export function apagar(chave: string): void {
  try {
    window.localStorage.removeItem(chave);
  } catch {
    // idem
  }
  window.dispatchEvent(new Event(EVENTO));
}

export function assinar(aoMudar: () => void): () => void {
  window.addEventListener("storage", aoMudar);
  window.addEventListener(EVENTO, aoMudar);
  return () => {
    window.removeEventListener("storage", aoMudar);
    window.removeEventListener(EVENTO, aoMudar);
  };
}
