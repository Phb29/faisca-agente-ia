"use client";

import { useRef, useState } from "react";
import { mensagemDeErro, type Conversa, type Pedido } from "@/lib/api";
import { useConversa } from "@/hooks/useConversa";
import { Aviso } from "@/components/ui/Aviso";
import { BoasVindas } from "./BoasVindas";
import { Cabecalho } from "./Cabecalho";
import { Compositor } from "./Compositor";
import { ListaDeMensagens } from "./ListaDeMensagens";
import { PainelDeContexto, type EstadoDoPainel } from "./PainelDeContexto";
import type { ClienteEscolhido } from "./TelaDeEntrada";

type Props = {
  cliente: ClienteEscolhido;
  /** Null na tela de boas-vindas: a Conversa nasce com a primeira mensagem. */
  conversaId: string | null;
  conversa: Conversa | null;
  pedidos: Pedido[] | null;
  mensagemInicial?: string;
  painel: EstadoDoPainel;
  aoComecar: (texto: string) => Promise<void>;
  aoAtualizar: () => void;
  aoAbrirMenu: () => void;
};

/**
 * Uma Conversa aberta: cabeçalho, mensagens, compositor e painel de contexto.
 * Quem usa passa `key={conversaId}`, então trocar de Conversa começa do zero.
 */
export function AreaDaConversa({
  cliente,
  conversaId,
  conversa,
  pedidos,
  mensagemInicial,
  painel,
  aoComecar,
  aoAtualizar,
  aoAbrirMenu,
}: Props) {
  const estado = useConversa({ clienteId: cliente.id, conversaId, mensagemInicial, aoAtualizar });
  const [rascunho, setRascunho] = useState("");
  const [erroAoComecar, setErroAoComecar] = useState<string | null>(null);
  const campo = useRef<HTMLTextAreaElement>(null);

  async function enviar(texto: string) {
    if (conversaId) return estado.enviar(texto);
    setErroAoComecar(null);
    try {
      await aoComecar(texto);
    } catch (erro) {
      setErroAoComecar(mensagemDeErro(erro));
      throw erro;
    }
  }

  function perguntarSobre(pedido: Pedido) {
    setRascunho(`Qual o status do pedido ${pedido.id}?`);
    painel.fecharGaveta();
    campo.current?.focus();
  }

  const status = conversa?.status ?? null;
  const aprovacao = estado.aprovacao ?? (status === "aprovacao_pendente" ? "generica" : null);
  const semMensagens =
    estado.mensagens.length === 0 && estado.emConstrucao === null && !estado.aguardando;
  const mostrarBoasVindas = semMensagens && (!conversaId || estado.historicoCarregado);
  const erro = estado.erro ?? erroAoComecar;

  return (
    <>
      <main className="flex min-w-0 flex-1 flex-col">
        <Cabecalho
          titulo={conversa?.titulo || "Nova conversa"}
          status={status}
          conexao={conversaId ? estado.conexao : null}
          painelAberto={painel.aberto || painel.naGaveta}
          aoAbrirMenu={aoAbrirMenu}
          aoAlternarPainel={painel.alternar}
        />

        {mostrarBoasVindas ? (
          <BoasVindas
            nome={cliente.nome}
            clienteNovo={Boolean(cliente.novo)}
            pedidos={pedidos ?? []}
            aoEscolher={(texto) => void enviar(texto).catch(() => undefined)}
          />
        ) : (
          <ListaDeMensagens
            mensagens={estado.mensagens}
            emConstrucao={estado.emConstrucao}
            aguardando={estado.aguardando}
            acaoAtual={estado.acaoAtual}
            historicoCarregado={estado.historicoCarregado || !conversaId}
            aprovacao={aprovacao}
            status={status}
          />
        )}

        <div className="shrink-0 px-3 pb-3 sm:px-6 sm:pb-4">
          {erro && (
            <Aviso
              className="mx-auto mb-3 max-w-[760px]"
              aoDispensar={() => {
                estado.dispensarErro();
                setErroAoComecar(null);
              }}
            >
              {erro}
            </Aviso>
          )}
          <Compositor
            campo={campo}
            valor={rascunho}
            aoMudar={setRascunho}
            aoEnviar={enviar}
            ocupado={estado.ocupada}
            bloqueio={aprovacao ? "Aguardando a decisão do Atendente sobre o Reembolso." : null}
          />
        </div>
      </main>

      <PainelDeContexto
        painel={painel}
        nomeDoCliente={cliente.nome}
        pedidos={pedidos}
        passos={estado.passos}
        desfecho={estado.desfecho}
        trabalhando={estado.ocupada}
        aoUsarPedido={perguntarSobre}
      />
    </>
  );
}
