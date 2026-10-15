"use client";

import { useCallback, useState } from "react";
import { criarConversa, listarConversas, listarPedidos } from "@/lib/api";
import { CHAVES } from "@/lib/armazenamento";
import { useArmazenado } from "@/hooks/useArmazenado";
import { useRecurso } from "@/hooks/useRecurso";
import { Gaveta } from "@/components/ui/Gaveta";
import { AreaDaConversa } from "./AreaDaConversa";
import { BarraLateral } from "./BarraLateral";
import type { Aba, EstadoDoPainel } from "./PainelDeContexto";
import type { ClienteEscolhido } from "./TelaDeEntrada";

const TELA_LARGA = "(min-width: 1280px)";

/** Coluna de contexto aberta ou fechada (lembrada entre visitas) e gaveta nas telas estreitas. */
function usePainel(): EstadoDoPainel {
  const preferencia = useArmazenado<boolean>(CHAVES.painelAberto);
  const [naGaveta, setNaGaveta] = useState(false);
  const [aba, setAba] = useState<Aba>("pedidos");
  const aberto = preferencia.valor ?? true;
  const definirPreferencia = preferencia.definir;

  const alternar = useCallback(() => {
    if (window.matchMedia(TELA_LARGA).matches) definirPreferencia(!aberto);
    else setNaGaveta((atual) => !atual);
  }, [aberto, definirPreferencia]);

  const fecharGaveta = useCallback(() => setNaGaveta(false), []);
  const fechar = useCallback(() => {
    setNaGaveta(false);
    definirPreferencia(false);
  }, [definirPreferencia]);

  return { aberto, naGaveta, aba, definirAba: setAba, alternar, fechar, fecharGaveta };
}

type Props = { cliente: ClienteEscolhido; aoSair: () => void };

export function Chat({ cliente, aoSair }: Props) {
  const conversas = useRecurso(`conversas:${cliente.id}`, () => listarConversas(cliente.id));
  const pedidos = useRecurso(`pedidos:${cliente.id}`, () => listarPedidos(cliente.id));
  const painel = usePainel();
  const [ativaId, setAtivaId] = useState<string | null>(null);
  const [inicio, setInicio] = useState<{ conversaId: string; texto: string } | null>(null);
  const [menuAberto, setMenuAberto] = useState(false);

  const recarregarConversas = conversas.recarregar;
  const aoAtualizar = useCallback(() => void recarregarConversas(), [recarregarConversas]);
  const fecharMenu = useCallback(() => setMenuAberto(false), []);

  function selecionar(id: string | null) {
    setInicio(null);
    setAtivaId(id);
    setMenuAberto(false);
  }

  /** A Conversa nasce com a primeira mensagem, que segue para a área recém-montada. */
  async function comecar(texto: string) {
    const { id } = await criarConversa(cliente.id);
    setInicio({ conversaId: id, texto });
    setAtivaId(id);
    void recarregarConversas();
  }

  const barra = (
    <BarraLateral
      cliente={cliente}
      conversas={conversas.dados}
      ativaId={ativaId}
      aoSelecionar={selecionar}
      aoNova={() => selecionar(null)}
      aoSair={aoSair}
    />
  );

  return (
    <div className="flex h-dvh overflow-hidden">
      <div className="hidden w-[280px] shrink-0 lg:flex">{barra}</div>
      <Gaveta aberta={menuAberto} aoFechar={fecharMenu} lado="esquerda" rotulo="Conversas" className="lg:hidden">
        {barra}
      </Gaveta>

      <div className="flex min-w-0 flex-1 lg:py-2 lg:pr-2">
        <div className="flex min-w-0 flex-1 overflow-hidden bg-surface lg:rounded-2xl lg:shadow-elevada lg:ring-1 lg:ring-line">
          <AreaDaConversa
            key={ativaId ?? "nova"}
            cliente={cliente}
            conversaId={ativaId}
            conversa={conversas.dados?.find((c) => c.id === ativaId) ?? null}
            pedidos={pedidos.dados}
            mensagemInicial={inicio?.conversaId === ativaId ? inicio.texto : undefined}
            painel={painel}
            aoComecar={comecar}
            aoAtualizar={aoAtualizar}
            aoAbrirMenu={() => setMenuAberto(true)}
          />
        </div>
      </div>
    </div>
  );
}
