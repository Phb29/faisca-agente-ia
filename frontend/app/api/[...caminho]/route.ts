// O resto da api, repassado: `/api/x` vira `${API_INTERNA}/x`, com o token da sessão (que
// vem do cookie) no Authorization e o IP do navegador no X-Ip-Do-Cliente. Só passa uma
// lista curta de cabeçalhos, nos dois sentidos. O corpo da resposta segue em stream, sem
// juntar nada: o SSE precisa chegar ao navegador evento a evento.

import { NextResponse, type NextRequest } from "next/server";
import {
  apagarCookie,
  baseDaApi,
  ipDoCliente,
  recusarOrigemDeFora,
  tokenDaSessao,
} from "@/lib/servidor/sessao";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CABECALHOS_DE_IDA = ["content-type", "accept", "last-event-id", "x-cliente-id"];
const CABECALHOS_DE_VOLTA = ["content-type", "cache-control", "retry-after", "x-accel-buffering"];
/** Status que, pelo padrão do fetch, não podem ter corpo. */
const SEM_CORPO = new Set([101, 204, 205, 304]);

async function repassar(request: NextRequest): Promise<Response> {
  const recusa = recusarOrigemDeFora(request);
  if (recusa) return recusa;

  // Concatenado, nunca `new URL(caminho, base)`: um `//outro-host` no caminho não troca o destino.
  const caminho = request.nextUrl.pathname.replace(/^\/api(?=\/|$)/, "") || "/";
  const destino = `${baseDaApi()}${caminho}${request.nextUrl.search}`;

  const ida = new Headers();
  for (const nome of CABECALHOS_DE_IDA) {
    const valor = request.headers.get(nome);
    if (valor !== null) ida.set(nome, valor);
  }
  const token = tokenDaSessao(request);
  if (token) ida.set("authorization", `Bearer ${token}`);
  const ip = ipDoCliente(request);
  if (ip) ida.set("x-ip-do-cliente", ip);

  const temCorpo = request.method !== "GET" && request.method !== "HEAD";
  let resposta: Response;
  try {
    resposta = await fetch(destino, {
      method: request.method,
      headers: ida,
      body: temCorpo ? await request.arrayBuffer() : undefined,
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
  if (resposta.status === 401 && token) apagarCookie(saida);
  return saida;
}

export const GET = repassar;
export const POST = repassar;
export const PUT = repassar;
export const PATCH = repassar;
export const DELETE = repassar;
