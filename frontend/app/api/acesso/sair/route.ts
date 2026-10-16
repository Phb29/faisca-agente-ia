// Logout: encerra a sessão na api e apaga o cookie. Idempotente, como a rota da api.

import { NextResponse, type NextRequest } from "next/server";
import { apagarCookie, baseDaApi, recusarOrigemDeFora, tokenDaSessao } from "@/lib/servidor/sessao";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const recusa = recusarOrigemDeFora(request);
  if (recusa) return recusa;

  const token = tokenDaSessao(request);
  if (token) {
    try {
      await fetch(`${baseDaApi()}/acesso/sair`, {
        method: "POST",
        headers: { authorization: `Bearer ${token}` },
        cache: "no-store",
      });
    } catch {
      // api fora do ar: o cookie sai do navegador mesmo assim, e a sessão expira sozinha
    }
  }

  const saida = new NextResponse(null, { status: 204, headers: { "cache-control": "no-store" } });
  apagarCookie(saida);
  return saida;
}
