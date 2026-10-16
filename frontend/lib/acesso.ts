// O lado do navegador do login. A sessão é um cookie HttpOnly que só o servidor do frontend
// lê, então aqui não há token nenhum: só navegação para a tela de entrada e de volta.

export const ENTRADA = "/entrar";

let indoParaEntrada = false;

/** A api recusou a sessão (401): vai para a tela de entrada, guardando onde estava. */
export function irParaEntrada(): void {
  if (typeof window === "undefined" || indoParaEntrada) return;
  const { pathname, search } = window.location;
  if (pathname === ENTRADA) return;
  indoParaEntrada = true;
  const parametros = new URLSearchParams({ proximo: pathname + search, motivo: "sessao" });
  window.location.assign(`${ENTRADA}?${parametros}`);
}

/** Encerra a sessão (o servidor apaga o cookie) e vai para a tela de entrada. */
export async function sair(): Promise<void> {
  try {
    await fetch("/api/acesso/sair", { method: "POST", cache: "no-store" });
  } catch {
    // sem rede: a tela de entrada aparece mesmo assim
  }
  window.location.replace(ENTRADA);
}

const BASE_FICTICIA = "https://ampere.invalid";

/**
 * Para onde ir depois do login. Só caminhos internos: começam com uma barra e nunca com
 * duas, nem com barra invertida ou caractere de controle, que o navegador transforma em
 * barra ou descarta. Qualquer outra coisa vira `/`.
 */
export function destinoSeguro(proximo: string | null): string {
  if (!proximo || !proximo.startsWith("/") || proximo.startsWith("//")) return "/";
  for (const letra of proximo) {
    const codigo = letra.charCodeAt(0);
    if (letra === "\\" || codigo < 0x20 || codigo === 0x7f) return "/";
  }
  let url: URL;
  try {
    url = new URL(proximo, BASE_FICTICIA);
  } catch {
    return "/";
  }
  if (url.origin !== BASE_FICTICIA) return "/";
  if (url.pathname === ENTRADA || url.pathname.startsWith("/api/")) return "/";
  return url.pathname + url.search + url.hash;
}
