"use client";

import { Suspense, useState } from "react";
import { CHAVES } from "@/lib/armazenamento";
import { useArmazenado } from "@/hooks/useArmazenado";
import { Login } from "@/components/atendente/Login";
import { Avaliacao } from "@/components/avaliacao/Avaliacao";

export default function PaginaDaAvaliacao() {
  // A aba fica na URL (`useSearchParams`), e o Next 15 exige um Suspense em volta disso.
  return (
    <Suspense fallback={null}>
      <ConteudoDaAvaliacao />
    </Suspense>
  );
}

/** O mesmo token da Central do Atendente: quem entrou numa não precisa entrar de novo. */
function ConteudoDaAvaliacao() {
  const token = useArmazenado<string>(CHAVES.tokenDoAtendente);
  const [motivoDaSaida, setMotivoDaSaida] = useState<string | null>(null);

  if (!token.hidratado) return null;
  if (!token.valor) {
    return (
      <Login
        titulo="Avaliação"
        descricao="Os três evals do chatbot, para projetar na aula, e a amostra ao vivo."
        aviso={motivoDaSaida}
        aoEntrar={(valor) => {
          setMotivoDaSaida(null);
          token.definir(valor);
        }}
      />
    );
  }
  return (
    <Avaliacao
      token={token.valor}
      aoSair={(motivo) => {
        setMotivoDaSaida(motivo ?? null);
        token.definir(null);
      }}
    />
  );
}
