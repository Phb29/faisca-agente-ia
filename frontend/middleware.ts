// Página sem o cookie da sessão vai para /entrar, guardando o caminho em `proximo`. Aqui só
// se olha se o cookie existe: quem decide se a sessão vale é a api, e um 401 dela também
// leva o navegador para /entrar.

import { NextResponse, type NextRequest } from "next/server";
import { NOME_DO_COOKIE, origemPublica } from "@/lib/servidor/sessao";

export function middleware(request: NextRequest) {
  if (request.cookies.has(NOME_DO_COOKIE)) return NextResponse.next();

  const { pathname, search } = request.nextUrl;
  // Absoluta e com a origem pública: atrás do proxy, a URL da requisição diz 0.0.0.0:3000.
  const entrada = new URL("/entrar", origemPublica(request));
  if (pathname !== "/") entrada.searchParams.set("proximo", pathname + search);
  return NextResponse.redirect(entrada);
}

export const config = {
  // Fora: a própria /entrar, as rotas do BFF (que respondem 401 sozinhas), os arquivos do
  // Next e qualquer arquivo estático com extensão (icon.svg, favicon.ico, imagens).
  matcher: ["/((?!entrar|api/|api$|_next/|.*\\.[a-zA-Z0-9]+$).*)"],
};
