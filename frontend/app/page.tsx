"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  criarConversa,
  enviarMensagem,
  listarConversas,
  listarMensagens,
  type Conversa,
  type Mensagem,
} from "@/lib/api";
import {
  conectarStream,
  type EventoApprovalRequired,
  type NomeDaAcao,
} from "@/lib/sse";
import {
  CHAVE_CLIENTE,
  apagarLocal,
  gerarId,
  gravarLocal,
  lerLocal,
} from "@/lib/local";
import { SeletorDeCliente, type ClienteEscolhido } from "@/components/SeletorDeCliente";
import { BadgeDeStatus, ListaDeConversas } from "@/components/ListaDeConversas";
import { Mensagens } from "@/components/Mensagens";
import { CaixaDeEnvio } from "@/components/CaixaDeEnvio";
import { IndicadorDeAcao } from "@/components/IndicadorDeAcao";
import { AvisoDeAprovacao } from "@/components/AvisoDeAprovacao";

export default function PaginaDoChat() {
  const [hidratado, setHidratado] = useState(false);
  const [cliente, setCliente] = useState<ClienteEscolhido | null>(null);

  const [conversas, setConversas] = useState<Conversa[]>([]);
  const [carregandoConversas, setCarregandoConversas] = useState(false);
  const [conversaAtivaId, setConversaAtivaId] = useState<string | null>(null);
  const [menuAberto, setMenuAberto] = useState(false);

  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [carregandoMensagens, setCarregandoMensagens] = useState(false);
  const [emConstrucao, setEmConstrucao] = useState<string | null>(null);
  const [aguardandoResposta, setAguardandoResposta] = useState(false);
  const [acaoAtual, setAcaoAtual] = useState<NomeDaAcao | null>(null);
  const [aprovacao, setAprovacao] = useState<EventoApprovalRequired | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [conexao, setConexao] = useState<"aberta" | "reconectando" | null>(null);

  const fecharStream = useRef<(() => void) | null>(null);

  // Cliente guardado em localStorage
  useEffect(() => {
    setCliente(lerLocal<ClienteEscolhido>(CHAVE_CLIENTE));
    setHidratado(true);
  }, []);

  const escolherCliente = useCallback((escolhido: ClienteEscolhido) => {
    gravarLocal(CHAVE_CLIENTE, escolhido);
    setCliente(escolhido);
    setConversaAtivaId(null);
    setConversas([]);
    setMensagens([]);
  }, []);

  function sairDoCliente() {
    apagarLocal(CHAVE_CLIENTE);
    fecharStream.current?.();
    fecharStream.current = null;
    setCliente(null);
    setConversaAtivaId(null);
    setConversas([]);
    setMensagens([]);
    setErro(null);
  }

  const recarregarConversas = useCallback(async () => {
    if (!cliente) return;
    setCarregandoConversas(true);
    try {
      const lista = await listarConversas(cliente.id);
      setConversas(lista);
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setCarregandoConversas(false);
    }
  }, [cliente]);

  useEffect(() => {
    void recarregarConversas();
  }, [recarregarConversas]);

  // Ao trocar de Conversa: carrega o histórico e abre o stream
  useEffect(() => {
    if (!cliente || !conversaAtivaId) return;
    const clienteId = cliente.id;
    const conversaId = conversaAtivaId;
    let ativo = true;

    setMensagens([]);
    setEmConstrucao(null);
    setAguardandoResposta(false);
    setAcaoAtual(null);
    setAprovacao(null);
    setErro(null);
    setCarregandoMensagens(true);

    listarMensagens(clienteId, conversaId)
      .then((historico) => {
        if (!ativo) return;
        setMensagens(historico);
      })
      .catch((e: Error) => ativo && setErro(e.message))
      .finally(() => ativo && setCarregandoMensagens(false));

    const fechar = conectarStream(conversaId, clienteId, {
      onConexao: (estado) => ativo && setConexao(estado),
      onToken: ({ texto }) => {
        if (!ativo) return;
        setAguardandoResposta(false);
        setEmConstrucao((atual) => (atual ?? "") + texto);
      },
      onToolCall: ({ nome }) => {
        if (!ativo) return;
        setAguardandoResposta(false);
        setAcaoAtual(nome);
      },
      onApprovalRequired: (dados) => {
        if (!ativo) return;
        setAcaoAtual(null);
        setAguardandoResposta(false);
        setAprovacao(dados);
        void recarregarConversas();
      },
      onMessageDone: ({ mensagem_id, conteudo }) => {
        if (!ativo) return;
        // Substitui pela versão final; se a mensagem ainda não existe localmente
        // (buffer perdido numa queda de conexão, por exemplo), acrescenta.
        setMensagens((atuais) => {
          const existe = atuais.some((m) => m.id === mensagem_id);
          if (existe) {
            return atuais.map((m) =>
              m.id === mensagem_id ? { ...m, conteudo } : m,
            );
          }
          return [
            ...atuais,
            {
              id: mensagem_id,
              papel: "assistente",
              conteudo,
              criada_em: new Date().toISOString(),
            },
          ];
        });
        setEmConstrucao(null);
        setAguardandoResposta(false);
        setAcaoAtual(null);
        setAprovacao(null);
        void recarregarConversas();
      },
      onError: ({ mensagem }) => {
        if (!ativo) return;
        setErro(mensagem);
        setAguardandoResposta(false);
        setAcaoAtual(null);
      },
    });
    fecharStream.current = fechar;

    return () => {
      ativo = false;
      fechar();
      if (fecharStream.current === fechar) fecharStream.current = null;
      setConexao(null);
    };
  }, [cliente, conversaAtivaId, recarregarConversas]);

  async function novaConversa() {
    if (!cliente) return;
    setErro(null);
    try {
      const { id } = await criarConversa(cliente.id);
      await recarregarConversas();
      setConversaAtivaId(id);
      setMenuAberto(false);
    } catch (e) {
      setErro((e as Error).message);
    }
  }

  async function enviar(conteudo: string) {
    if (!cliente || !conversaAtivaId) return;
    const messageId = gerarId();
    setErro(null);
    setMensagens((atuais) => [
      ...atuais,
      {
        id: messageId,
        papel: "cliente",
        conteudo,
        criada_em: new Date().toISOString(),
      },
    ]);
    setAguardandoResposta(true);
    try {
      await enviarMensagem(cliente.id, conversaAtivaId, {
        message_id: messageId,
        conteudo,
      });
    } catch (e) {
      setAguardandoResposta(false);
      setErro((e as Error).message);
      throw e;
    }
  }

  if (!hidratado) return null;

  if (!cliente) {
    return <SeletorDeCliente aoEscolher={escolherCliente} />;
  }

  const conversaAtiva = conversas.find((c) => c.id === conversaAtivaId) ?? null;

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col md:flex-row">
      {/* Barra lateral */}
      <aside
        className={`${menuAberto ? "block" : "hidden"} w-full shrink-0 border-b border-stone-200 bg-stone-50 md:block md:w-72 md:border-r md:border-b-0`}
      >
        <div className="flex items-center justify-between border-b border-stone-200 px-3 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{cliente.nome}</p>
            <p className="truncate text-[11px] text-stone-500">{cliente.id}</p>
          </div>
          <button
            type="button"
            onClick={sairDoCliente}
            className="text-xs text-stone-500 underline-offset-2 hover:text-stone-900 hover:underline"
          >
            Trocar
          </button>
        </div>
        <div className="h-[calc(100vh-11rem)] md:h-[calc(100vh-8.5rem)]">
          <ListaDeConversas
            conversas={conversas}
            conversaAtivaId={conversaAtivaId}
            carregando={carregandoConversas}
            aoSelecionar={(id) => {
              setConversaAtivaId(id);
              setMenuAberto(false);
            }}
            aoCriar={() => void novaConversa()}
          />
        </div>
      </aside>

      {/* Área principal */}
      <section className="flex min-h-[calc(100vh-3.5rem)] flex-1 flex-col md:h-[calc(100vh-3.5rem)] md:min-h-0">
        <div className="flex items-center justify-between gap-2 border-b border-stone-200 bg-white px-4 py-2.5">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              onClick={() => setMenuAberto((v) => !v)}
              className="rounded-lg border border-stone-300 px-2 py-1 text-xs md:hidden"
            >
              Conversas
            </button>
            <h1 className="truncate text-sm font-semibold">
              {conversaAtiva
                ? conversaAtiva.titulo || "Conversa"
                : "Selecione uma Conversa"}
            </h1>
            {conversaAtiva && <BadgeDeStatus status={conversaAtiva.status} />}
          </div>
          {conexao === "reconectando" && (
            <span className="text-[11px] text-stone-500">Reconectando…</span>
          )}
        </div>

        {erro && (
          <div className="flex items-start justify-between gap-3 border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800">
            <span>{erro}</span>
            <button
              type="button"
              onClick={() => setErro(null)}
              className="text-xs underline"
            >
              fechar
            </button>
          </div>
        )}

        <AvisoDeAprovacao aprovacao={aprovacao} />

        {conversaAtivaId ? (
          <Mensagens
            mensagens={mensagens}
            emConstrucao={emConstrucao}
            aguardandoResposta={aguardandoResposta}
            carregando={carregandoMensagens}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center px-4 text-center text-sm text-stone-500">
            Escolha uma Conversa na lista ou clique em &ldquo;Nova Conversa&rdquo;.
          </div>
        )}

        <IndicadorDeAcao acao={acaoAtual} />
        <CaixaDeEnvio desabilitada={!conversaAtivaId} aoEnviar={enviar} />
      </section>
    </div>
  );
}
