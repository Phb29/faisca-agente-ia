// Peças do BFF que só rodam no servidor do frontend: o cookie da sessão, o endereço da api
// na rede interna, o segredo que a api exige do BFF, o IP do navegador, o limite do corpo e
// a conferência de origem contra CSRF. O token da sessão mora só no cookie HttpOnly; o
// JavaScript da página nunca o vê.

import "server-only";
import { NextResponse, type NextRequest } from "next/server";

const PRODUCAO = process.env.NODE_ENV === "production";
const SEM_CACHE = { "cache-control": "no-store" };

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

/** O token que a api dá é base64url. Qualquer outra coisa no cookie conta como sem sessão. */
const FORMATO_DO_TOKEN = /^[A-Za-z0-9_-]{16,128}$/;

export function tokenDaSessao(request: NextRequest): string | null {
  const valor = request.cookies.get(NOME_DO_COOKIE)?.value;
  return valor && FORMATO_DO_TOKEN.test(valor) ? valor : null;
}

/**
 * O 401 de quem chega sem sessão, sem ler o corpo e sem chamar a api. Um cookie ilegível
 * também sai, para o middleware voltar a mandar para /entrar.
 */
export function semSessao(): NextResponse {
  const resposta = NextResponse.json(
    { detail: "Sessão inválida ou expirada." },
    { status: 401, headers: SEM_CACHE },
  );
  apagarCookie(resposta);
  return resposta;
}

// ---------- A api ----------

let avisouSemApi = false;

/**
 * A api pela rede interna. Lida a cada chamada, porque é variável de execução, não de build.
 * Em desenvolvimento, o padrão é o localhost. Em produção não há padrão: sem `API_INTERNA`,
 * devolve null e avisa no log, e quem chamou responde 502 (`apiNaoConfigurada`).
 */
export function baseDaApi(): string | null {
  const base = process.env.API_INTERNA?.trim();
  if (base) return base.replace(/\/+$/, "");
  if (!PRODUCAO) return "http://localhost:8000";
  if (!avisouSemApi) {
    avisouSemApi = true;
    console.error("[bff] API_INTERNA não configurada: o frontend não tem como falar com a api.");
  }
  return null;
}

export const apiNaoConfigurada = (): NextResponse =>
  NextResponse.json({ detail: "API_INTERNA não configurada." }, { status: 502, headers: SEM_CACHE });

/**
 * Cabeçalhos de toda chamada à api. Começam vazios, então nada do navegador passa sem
 * querer, e levam o `X-Bff-Segredo` quando `BFF_SEGREDO` está configurado: com ele, a api
 * só atende quem conhece o segredo, ou seja, este servidor.
 */
export function cabecalhosParaApi(): Headers {
  const cabecalhos = new Headers();
  const segredo = process.env.BFF_SEGREDO?.trim();
  if (segredo) cabecalhos.set("x-bff-segredo", segredo);
  return cabecalhos;
}

// ---------- O navegador ----------

/** Último valor de um cabeçalho que pode vir como lista ("a, b"). */
const ultimo = (valor: string | null): string | null => valor?.split(",").at(-1)?.trim() || null;

const TAMANHO_MAXIMO_DO_IP = 64;

/**
 * O IP do navegador. Primeiro o `X-Real-IP`, que a borda do Railway põe. Senão, o ÚLTIMO
 * item do `X-Forwarded-For`, que é o que a borda acrescentou. Nunca o primeiro: esse vem
 * de quem fez a requisição, pode ser inventado à vontade, e furaria o limite de tentativas
 * por IP da api.
 */
export function ipDoCliente(request: NextRequest): string | null {
  const ip = ultimo(request.headers.get("x-real-ip")) ?? ultimo(request.headers.get("x-forwarded-for"));
  return ip ? ip.slice(0, TAMANHO_MAXIMO_DO_IP) : null;
}

/** Primeiro valor de um cabeçalho que pode vir como lista ("a, b"). */
const primeiro = (valor: string | null): string | null => valor?.split(",")[0]?.trim() || null;

/**
 * A origem fixa em `ORIGEM_PUBLICA`, como `https://seu-frontend.up.railway.app`.
 * Valor ilegível derruba a requisição com erro no log: melhor falhar do que confiar errado.
 */
function origemConfigurada(): string | null {
  const valor = process.env.ORIGEM_PUBLICA?.trim();
  if (!valor) return null;
  try {
    return new URL(valor).origin;
  } catch {
    throw new Error(`[bff] ORIGEM_PUBLICA inválida: "${valor}". Use algo como https://exemplo.com.`);
  }
}

/**
 * A origem pública do frontend, como o navegador a vê. Com `ORIGEM_PUBLICA`, é ela, e
 * nenhum cabeçalho da requisição conta. Sem ela (no desenvolvimento), vale o que os
 * cabeçalhos dizem: atrás do proxy do Railway, a URL da requisição diz `0.0.0.0:3000`, e o
 * host e o protocolo de verdade vêm nos X-Forwarded-*.
 */
export function origemPublica(request: NextRequest): string {
  const fixa = origemConfigurada();
  if (fixa) return fixa;
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
  return NextResponse.json({ detail: "Origem não permitida." }, { status: 403, headers: SEM_CACHE });
}

// ---------- O corpo ----------

/** Limite do corpo nas rotas repassadas. O maior corpo do app é uma Memória Procedural. */
export const LIMITE_DO_CORPO = 1024 * 1024;
/** Limite do corpo do login: e-mail e senha cabem com folga. */
export const LIMITE_DO_LOGIN = 64 * 1024;

const grandeDemais = (): NextResponse =>
  NextResponse.json({ detail: "Corpo da requisição grande demais." }, { status: 413, headers: SEM_CACHE });

/**
 * Lê o corpo até `limite` bytes. A rota do Next não tem limite próprio, e um
 * `arrayBuffer()` puxaria qualquer tamanho para a memória. Recusa com 413 logo de cara,
 * pelo `Content-Length`, ou no meio da leitura, quando o corpo vem em partes (chunked) e
 * passa do limite. Devolve os bytes, ou a resposta a dar.
 */
export async function lerCorpo(request: NextRequest, limite: number): Promise<Uint8Array<ArrayBuffer> | NextResponse> {
  if (Number(request.headers.get("content-length")) > limite) return grandeDemais();
  if (!request.body) return new Uint8Array(0);

  const leitor = request.body.getReader();
  const partes: Uint8Array[] = [];
  let total = 0;
  try {
    for (;;) {
      const { value, done } = await leitor.read();
      if (done) break;
      total += value.byteLength;
      if (total > limite) {
        leitor.cancel().catch(() => undefined);
        return grandeDemais();
      }
      partes.push(value);
    }
  } catch {
    return NextResponse.json({ detail: "Não foi possível ler o corpo." }, { status: 400, headers: SEM_CACHE });
  }

  const corpo = new Uint8Array(total);
  let posicao = 0;
  for (const parte of partes) {
    corpo.set(parte, posicao);
    posicao += parte.byteLength;
  }
  return corpo;
}
