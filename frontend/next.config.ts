import type { NextConfig } from "next";

const PRODUCAO = process.env.NODE_ENV === "production";

// O Next põe scripts e estilos inline para hidratar a página, daí o 'unsafe-inline'. Tudo o
// mais é da própria origem: as fontes são servidas pelo Next, e a api só se alcança pelo BFF.
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const CABECALHOS = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  // Só em produção: o localhost é http, e o dev server do Next precisa de eval e websocket.
  ...(PRODUCAO
    ? [
        { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
        { key: "Content-Security-Policy", value: CSP },
      ]
    : []),
];

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:caminho*", headers: CABECALHOS }];
  },
};

export default nextConfig;
