"use client";

import { CHAVES } from "@/lib/armazenamento";
import { useArmazenado } from "@/hooks/useArmazenado";
import { Chat } from "@/components/chat/Chat";
import { TelaDeEntrada, type ClienteEscolhido } from "@/components/chat/TelaDeEntrada";

export default function PaginaDoChat() {
  const cliente = useArmazenado<ClienteEscolhido>(CHAVES.cliente);

  if (!cliente.hidratado) return null;
  if (!cliente.valor) return <TelaDeEntrada aoEscolher={cliente.definir} />;
  return <Chat key={cliente.valor.id} cliente={cliente.valor} aoSair={() => cliente.definir(null)} />;
}
