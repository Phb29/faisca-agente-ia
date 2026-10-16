// O resto da api, repassado: `/api/x` vira `${API_INTERNA}/x`, com o token da sessão (que
// vem do cookie) no Authorization, o IP do navegador no X-Ip-Do-Cliente e o segredo do BFF
// no X-Bff-Segredo. Só passam os caminhos que o app usa e uma lista curta de cabeçalhos,
// nos dois sentidos. O corpo da resposta segue em stream, sem juntar nada: o SSE precisa
// chegar ao navegador evento a evento.

import { NextResponse, type NextRequest } from "next/server";
import {
  LIMITE_DO_CORPO,
  apagarCookie,
  apiNaoConfigurada,
  baseDaApi,
  cabecalhosParaApi,
  ipDoCliente,
  lerCorpo,
  recusarOrigemDeFora,
  semSessao,
  tokenDaSessao,
} from "@/lib/servidor/sessao";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * O primeiro trecho de cada caminho que o app chama (`lib/api.ts`, os dois streams). O resto
 * da api, como `/health`, `/docs` e `/openapi.json`, não existe para o navegador.
 */
const PREFIXOS = new Set(["clientes", "pedidos", "conversas", "atendente", "avaliacao"]);
/** Caminhos exatos fora daqueles prefixos. `/acesso/entrar` e `/acesso/sair` têm rota própria. */
const CAMINHOS = new Set(["/acesso/eu"]);

const CABECALHOS_DE_IDA = ["content-type", "accept", "last-event-id", "x-cliente-id"];
const CABECALHOS_DE_VOLTA = ["content-type", "cache-control", "retry-after", "x-accel-buffering"];
/** Status que, pelo padrão do fetch, não podem ter corpo. */
const SEM_CORPO = new Set([101, 204, 205, 304]);

/**
 * Um trecho seguro não é vazio, não vira `.` nem `..` e não esconde barra: o fetch
 * normalizaria um `%2e%2e` e o caminho sairia da lista sem ninguém ver.
 */
function trechoSeguro(trecho: string): boolean {
  let lido: string;
  try {
    lido = decodeURIComponent(trecho);
  } catch {
    return false;
  }
  return lido !== "" && lido !== "." && lido !== ".." && !/[/\\]/.test(lido);
}

function caminhoPermitido(caminho: string): boolean {
  if (CAMINHOS.has(caminho)) return true;
  const trechos = caminho.split("/").slice(1);
  return PREFIXOS.has(trechos[0]) && trechos.every(trechoSeguro);
}

const naoEncontrado = () =>
  NextResponse.json({ detail: "Not Found" }, { status: 404, headers: { "cache-control": "no-store" } });

async function repassar(request: NextRequest): Promise<Response> {
  const caminho = request.nextUrl.pathname.replace(/^\/api(?=\/|$)/, "") || "/";
  if (!caminhoPermitido(caminho)) return naoEncontrado();

  const recusa = recusarOrigemDeFora(request);
  if (recusa) return recusa;

  // Sem sessão, a resposta sai daqui: o corpo nem é lido, e a api nem é chamada.
  const token = tokenDaSessao(request);
  if (!token) return semSessao();

  const base = baseDaApi();
  if (!base) return apiNaoConfigurada();

  let corpo: Uint8Array<ArrayBuffer> | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    const lido = await lerCorpo(request, LIMITE_DO_CORPO);
    if (lido instanceof NextResponse) return lido;
    corpo = lido;
  }

  const ida = cabecalhosParaApi();
  for (const nome of CABECALHOS_DE_IDA) {
    const valor = request.headers.get(nome);
    if (valor !== null) ida.set(nome, valor);
  }
  ida.set("authorization", `Bearer ${token}`);
  const ip = ipDoCliente(request);
  if (ip) ida.set("x-ip-do-cliente", ip);

  let resposta: Response;
  try {
    // Concatenado, nunca `new URL(caminho, base)`: um `//outro-host` no caminho não troca o destino.
    resposta = await fetch(`${base}${caminho}${request.nextUrl.search}`, {
      method: request.method,
      headers: ida,
      body: corpo,
      // Fechar a aba aborta a requisição do navegador, e o abort fecha o SSE lá na api.
      signal: request.signal,
      cache: "no-store",
    });
  } catch {
    if (request.signal.aborted) return new Response(null, { status: 499 });
    return NextResponse.json({ detail: "Não foi possível falar com a API." }, { status: 502 });
  }

  const volta = new Headers();
  for (const nome of CABECALHOS_DE_VOLTA) {
    const valor = resposta.headers.get(nome);
    if (valor !== null) volta.set(nome, valor);
  }
  if (volta.get("content-type")?.startsWith("text/event-stream")) {
    // `no-transform` impede compressão e buffer no caminho (do Next e do proxy).
    volta.set("cache-control", "no-cache, no-transform");
    volta.set("x-accel-buffering", "no");
  }

  const saida = new NextResponse(SEM_CORPO.has(resposta.status) ? null : resposta.body, {
    status: resposta.status,
    headers: volta,
  });
  // Sessão recusada pela api: o cookie vencido sai, e o middleware passa a mandar para /entrar.
  if (resposta.status === 401) apagarCookie(saida);
  return saida;
}

export const GET = repassar;
export const POST = repassar;
export const PUT = repassar;
export const PATCH = repassar;
export const DELETE = repassar;
