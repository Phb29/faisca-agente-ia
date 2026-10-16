// Peças do BFF que só rodam no servidor do frontend: o cookie da sessão, o endereço da api
// na rede interna, o IP do navegador e a conferência de origem contra CSRF. O token da
// sessão mora só no cookie HttpOnly; o JavaScript da página nunca o vê.

import "server-only";
import { NextResponse, type NextRequest } from "next/server";

const PRODUCAO = process.env.NODE_ENV === "production";

/**
 * Em produção, o prefixo `__Host-` obriga Secure, Path=/ e nenhum Domain. O localhost é
 * http, então em desenvolvimento o cookie perde o prefixo e o Secure.
 */
export const NOME_DO_COOKIE = PRODUCAO ? "__Host-ampere_sessao" : "ampere_sessao";

const OPCOES_DO_COOKIE = {
  httpOnly: true,
  secure: PRODUCAO,
  sameSite: "strict",
  path: "/",
} as const;

export function gravarCookie(resposta: NextResponse, token: string, segundos: number): void {
  resposta.cookies.set(NOME_DO_COOKIE, token, { ...OPCOES_DO_COOKIE, maxAge: segundos });
}

/** Apaga com os mesmos atributos: um `__Host-` sem Secure seria recusado pelo navegador. */
export function apagarCookie(resposta: NextResponse): void {
  resposta.cookies.set(NOME_DO_COOKIE, "", { ...OPCOES_DO_COOKIE, maxAge: 0 });
}

export const tokenDaSessao = (request: NextRequest): string | null =>
  request.cookies.get(NOME_DO_COOKIE)?.value || null;

/** A api pela rede interna. Lida a cada chamada, porque é variável de execução, não de build. */
export function baseDaApi(): string {
  return (process.env.API_INTERNA || "http://localhost:8000").replace(/\/+$/, "");
}

/** Primeiro valor de um cabeçalho que pode vir como lista ("a, b"). */
const primeiro = (valor: string | null): string | null => valor?.split(",")[0]?.trim() || null;

/** O IP do navegador, que o proxy do Railway põe no X-Forwarded-For. */
export const ipDoCliente = (request: NextRequest): string | null =>
  primeiro(request.headers.get("x-forwarded-for")) ?? primeiro(request.headers.get("x-real-ip"));

/**
 * A origem pública do frontend, como o navegador a vê. Atrás do proxy do Railway, a URL da
 * requisição diz `0.0.0.0:3000`; o host e o protocolo de verdade vêm nos X-Forwarded-*.
 */
export function origemPublica(request: NextRequest): string {
  const host =
    primeiro(request.headers.get("x-forwarded-host")) ?? request.headers.get("host") ?? request.nextUrl.host;
  const protocolo =
    primeiro(request.headers.get("x-forwarded-proto")) ?? request.nextUrl.protocol.replace(/:$/, "");
  return `${protocolo}://${host}`;
}

function mesmaOrigem(a: string, b: string): boolean {
  try {
    return new URL(a).origin === new URL(b).origin;
  } catch {
    return false;
  }
}

/**
 * Contra CSRF, além do SameSite=Strict: o que não é GET nem HEAD só passa com o `Origin`
 * igual à origem do próprio frontend. Devolve o 403 a responder, ou null quando passa.
 */
export function recusarOrigemDeFora(request: NextRequest): NextResponse | null {
  if (request.method === "GET" || request.method === "HEAD") return null;
  const origem = request.headers.get("origin");
  if (origem && mesmaOrigem(origem, origemPublica(request))) return null;
  return NextResponse.json({ detail: "Origem não permitida." }, { status: 403 });
}
