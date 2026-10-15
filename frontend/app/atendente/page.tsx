"use client";

import { useState } from "react";
import { CHAVES } from "@/lib/armazenamento";
import { useArmazenado } from "@/hooks/useArmazenado";
import { Central } from "@/components/atendente/Central";
import { Login } from "@/components/atendente/Login";

export default function PaginaDoAtendente() {
  const token = useArmazenado<string>(CHAVES.tokenDoAtendente);
  const [motivoDaSaida, setMotivoDaSaida] = useState<string | null>(null);

  if (!token.hidratado) return null;
  if (!token.valor) {
    return (
      <Login
        aviso={motivoDaSaida}
        aoEntrar={(valor) => {
          setMotivoDaSaida(null);
          token.definir(valor);
        }}
      />
    );
  }
  return (
    <Central
      token={token.valor}
      aoSair={(motivo) => {
        setMotivoDaSaida(motivo ?? null);
        token.definir(null);
      }}
    />
  );
}
