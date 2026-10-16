// Login: repassa e-mail e senha para a api e, se ela aceitar, guarda o token num cookie
// HttpOnly. O navegador recebe só o e-mail; o token nunca sai do servidor do frontend.

import { NextResponse, type NextRequest } from "next/server";
import {
  LIMITE_DO_LOGIN,
  apiNaoConfigurada,
  baseDaApi,
  cabecalhosParaApi,
  gravarCookie,
  ipDoCliente,
  lerCorpo,
  recusarOrigemDeFora,
} from "@/lib/servidor/sessao";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Sessao = { token: string; email: string; expira_em: string };

const DOZE_HORAS_S = 12 * 60 * 60;
const SEM_CACHE = { "cache-control": "no-store" };

export async function POST(request: NextRequest) {
  const recusa = recusarOrigemDeFora(request);
  if (recusa) return recusa;

  const base = baseDaApi();
  if (!base) return apiNaoConfigurada();

  const corpo = await lerCorpo(request, LIMITE_DO_LOGIN);
  if (corpo instanceof NextResponse) return corpo;

  const cabecalhos = cabecalhosParaApi();
  cabecalhos.set("content-type", "application/json");
  cabecalhos.set("accept", "application/json");
  const ip = ipDoCliente(request);
  if (ip) cabecalhos.set("x-ip-do-cliente", ip);
  // A sessão guarda o navegador de quem entrou; sem isto, a api veria o fetch do Node.
  const navegador = request.headers.get("user-agent");
  if (navegador) cabecalhos.set("user-agent", navegador);

  let resposta: Response;
  try {
    resposta = await fetch(`${base}/acesso/entrar`, {
      method: "POST",
      headers: cabecalhos,
      body: corpo,
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "Não foi possível falar com a API." }, { status: 502, headers: SEM_CACHE });
  }

  if (resposta.status !== 200) {
    // 401, 429 (bloqueio por tentativas), 503 (rajada de logins) e qualquer outra recusa
    // voltam como vieram, com o Retry-After.
    const volta = new Headers(SEM_CACHE);
    volta.set("content-type", resposta.headers.get("content-type") ?? "application/json");
    const espera = resposta.headers.get("retry-after");
    if (espera) volta.set("retry-after", espera);
    return new NextResponse(await resposta.text(), { status: resposta.status, headers: volta });
  }

  const sessao = (await resposta.json()) as Sessao;
  const saida = NextResponse.json({ email: sessao.email }, { headers: SEM_CACHE });
  gravarCookie(saida, sessao.token, segundosAte(sessao.expira_em));
  return saida;
}

/** O cookie vive até a sessão expirar na api; data ilegível cai no padrão de 12 horas. */
function segundosAte(expiraEm: string): number {
  const segundos = Math.floor((Date.parse(expiraEm) - Date.now()) / 1000);
  return Number.isFinite(segundos) && segundos > 0 ? segundos : DOZE_HORAS_S;
}
