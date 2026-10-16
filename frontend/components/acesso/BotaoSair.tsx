"use client";

import { LogOut } from "lucide-react";
import { useState } from "react";
import { sair } from "@/lib/acesso";
import { Botao } from "@/components/ui/Botao";

/** Encerra a sessão: o servidor apaga o cookie e a tela de entrada aparece. */
export function BotaoSair({ className }: { className?: string }) {
  const [saindo, setSaindo] = useState(false);
  return (
    <Botao
      variante="fantasma"
      tamanho="sm"
      icone={LogOut}
      aria-label="Sair"
      title="Sair da conta"
      carregando={saindo}
      className={className}
      onClick={() => {
        setSaindo(true);
        void sair();
      }}
    >
      <span className="hidden sm:inline">Sair</span>
    </Botao>
  );
}
