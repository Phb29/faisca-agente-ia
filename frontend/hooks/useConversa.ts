"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import {
  enviarMensagem,
  listarMensagens,
  mensagemDeErro,
  type Desfecho,
  type Mensagem,
  type NoDoGrafo,
  type NomeDaAcao,
  type Papel,
} from "@/lib/api";
import { gerarId } from "@/lib/id";
import {
  conectarStream,
  type Conexao,
  type EventoApprovalRequired,
  type EventoDoStream,
} from "@/lib/sse";

// ---------- Estado ----------

export type MensagemNaTela = {
  id: string;
  papel: Papel;
  conteudo: string;
  criada_em: string;
  message_id?: string | null;
  /** Enviada pelo Cliente e ainda não confirmada pela API (202). */
  pendente?: boolean;
};

/** Um passo do turno atual, para os Bastidores: um nó do grafo ou uma Ação. */
export type Passo =
  | { id: string; tipo: "etapa"; no: NoDoGrafo; detalhe: string | null; alerta: boolean; em: string }
  | { id: string; tipo: "acao"; nome: NomeDaAcao; args: Record<string, unknown>; em: string };

export type EstadoDaConversa = {
  mensagens: MensagemNaTela[];
  historicoCarregado: boolean;
  /** Texto chegando token a token; null quando não há resposta em construção. */
  emConstrucao: string | null;
  /** Mensagem enviada, nenhum sinal do assistente ainda. */
  aguardando: boolean;
  acaoAtual: { nome: NomeDaAcao; args: Record<string, unknown> } | null;
  aprovacao: EventoApprovalRequired | null;
  passos: Passo[];
  /** O último turno terminou; o próximo sinal do assistente abre um turno novo. */
  turnoEncerrado: boolean;
  desfecho: Desfecho | null;
  erro: string | null;
  conexao: Conexao;
};

type Acao =
  | { tipo: "historico"; mensagens: Mensagem[] }
  | { tipo: "enviada"; mensagem: MensagemNaTela }
  | { tipo: "confirmada"; id: string; conteudo: string }
  | { tipo: "recusada"; id: string; erro: string }
  | { tipo: "evento"; evento: EventoDoStream; id: string; em: string }
  | { tipo: "conexao"; conexao: Conexao }
  | { tipo: "falha"; erro: string }
  | { tipo: "dispensar_erro" };

function mensagemDoCliente(conteudo: string): MensagemNaTela {
  const id = gerarId();
  return { id, message_id: id, papel: "cliente", conteudo, criada_em: new Date().toISOString(), pendente: true };
}

function estadoInicial(mensagemInicial?: string): EstadoDaConversa {
  return {
    mensagens: mensagemInicial ? [mensagemDoCliente(mensagemInicial)] : [],
    historicoCarregado: false,
    emConstrucao: null,
    aguardando: Boolean(mensagemInicial),
    acaoAtual: null,
    aprovacao: null,
    passos: [],
    turnoEncerrado: false,
    desfecho: null,
    erro: null,
    conexao: "conectando",
  };
}

/** Qualquer sinal do assistente depois de um turno encerrado abre um turno novo. */
function abrirTurno(estado: EstadoDaConversa): EstadoDaConversa {
  if (!estado.turnoEncerrado) return estado;
  return { ...estado, passos: [], turnoEncerrado: false, aprovacao: null, desfecho: null };
}

function aplicarEvento(
  estado: EstadoDaConversa,
  evento: EventoDoStream,
  id: string,
  em: string,
): EstadoDaConversa {
  switch (evento.tipo) {
    case "token": {
      const turno = abrirTurno(estado);
      return {
        ...turno,
        aguardando: false,
        acaoAtual: null,
        emConstrucao: (turno.emConstrucao ?? "") + evento.dados.texto,
      };
    }
    case "tool_call": {
      const turno = abrirTurno(estado);
      const { nome, args } = evento.dados;
      return {
        ...turno,
        aguardando: false,
        acaoAtual: { nome, args },
        passos: [...turno.passos, { id, tipo: "acao", nome, args, em }],
      };
    }
    case "etapa": {
      const turno = abrirTurno(estado);
      const { no, detalhe, alerta } = evento.dados;
      const passos = [...turno.passos, { id, tipo: "etapa" as const, no, detalhe, alerta, em }];
      // O Guardrail de saída reprovou a resposta: o texto que já apareceu é descartado.
      const descartada = no === "guardrail_saida" && alerta;
      return descartada
        ? { ...turno, passos, emConstrucao: null, aguardando: true }
        : { ...turno, passos };
    }
    case "approval_required":
      return {
        ...estado,
        aprovacao: evento.dados,
        aguardando: false,
        acaoAtual: null,
        emConstrucao: null,
        turnoEncerrado: true,
      };
    case "message_done": {
      const { mensagem_id, conteudo, reenvio, desfecho } = evento.dados;
      const existe = estado.mensagens.some((m) => m.id === mensagem_id);
      // Reenvio ao reconectar: só importa se a resposta ainda não está na tela.
      if (reenvio && existe) return estado;
      const mensagens = existe
        ? estado.mensagens.map((m) => (m.id === mensagem_id ? { ...m, conteudo } : m))
        : [...estado.mensagens, { id: mensagem_id, papel: "assistente" as const, conteudo, criada_em: em }];
      return {
        ...estado,
        mensagens,
        emConstrucao: null,
        aguardando: false,
        acaoAtual: null,
        aprovacao: null,
        turnoEncerrado: true,
        desfecho: desfecho ?? null,
      };
    }
    case "error":
      return {
        ...estado,
        erro: evento.dados.mensagem,
        emConstrucao: null,
        aguardando: false,
        acaoAtual: null,
        turnoEncerrado: true,
      };
  }
}

export function reduzirConversa(estado: EstadoDaConversa, acao: Acao): EstadoDaConversa {
  switch (acao.tipo) {
    case "historico": {
      // O histórico da API vence; ficam só as mensagens locais que ele ainda não conhece.
      const ids = new Set(acao.mensagens.map((m) => m.id));
      const messageIds = new Set(acao.mensagens.map((m) => m.message_id).filter(Boolean));
      const locais = estado.mensagens.filter((m) => !ids.has(m.id) && !messageIds.has(m.id));
      return { ...estado, mensagens: [...acao.mensagens, ...locais], historicoCarregado: true };
    }
    case "enviada":
      if (estado.mensagens.some((m) => m.id === acao.mensagem.id)) return estado;
      return {
        ...estado,
        mensagens: [...estado.mensagens, acao.mensagem],
        aguardando: true,
        emConstrucao: null,
        acaoAtual: null,
        passos: [],
        turnoEncerrado: false,
        desfecho: null,
        erro: null,
      };
    case "confirmada":
      return {
        ...estado,
        mensagens: estado.mensagens.map((m) =>
          m.id === acao.id ? { ...m, conteudo: acao.conteudo, pendente: false } : m,
        ),
      };
    case "recusada":
      return {
        ...estado,
        mensagens: estado.mensagens.filter((m) => m.id !== acao.id),
        aguardando: false,
        erro: acao.erro,
      };
    case "evento":
      return aplicarEvento(estado, acao.evento, acao.id, acao.em);
    case "conexao":
      return { ...estado, conexao: acao.conexao };
    case "falha":
      return { ...estado, erro: acao.erro };
    case "dispensar_erro":
      return { ...estado, erro: null };
  }
}

// ---------- Hook ----------

type Parametros = {
  clienteId: string;
  /** Null enquanto a Conversa não existe (tela de boas-vindas). */
  conversaId: string | null;
  /** Primeira mensagem de uma Conversa recém-criada, enviada assim que o stream abrir. */
  mensagemInicial?: string;
  /** Algo mudou no servidor (status, título): hora de recarregar a lista de Conversas. */
  aoAtualizar?: () => void;
};

/**
 * Uma Conversa ao vivo: histórico, stream SSE e envio idempotente. O componente que usa
 * este hook deve ter `key={conversaId}`, para cada Conversa começar de um estado limpo.
 */
export function useConversa({ clienteId, conversaId, mensagemInicial, aoAtualizar }: Parametros) {
  const [estado, despachar] = useReducer(reduzirConversa, mensagemInicial, estadoInicial);

  const aoAtualizarAtual = useRef(aoAtualizar);
  useEffect(() => {
    aoAtualizarAtual.current = aoAtualizar;
  });

  useEffect(() => {
    if (!conversaId) return;
    let ativo = true;

    listarMensagens(clienteId, conversaId)
      .then((mensagens) => ativo && despachar({ tipo: "historico", mensagens }))
      .catch((erro) => ativo && despachar({ tipo: "falha", erro: mensagemDeErro(erro) }));

    const fechar = conectarStream(clienteId, conversaId, {
      aoEvento: (evento) => {
        despachar({ tipo: "evento", evento, id: gerarId(), em: new Date().toISOString() });
        const mudouNoServidor =
          evento.tipo === "approval_required" ||
          (evento.tipo === "message_done" && !evento.dados.reenvio);
        if (mudouNoServidor) aoAtualizarAtual.current?.();
      },
      aoMudarConexao: (conexao) => despachar({ tipo: "conexao", conexao }),
    });

    return () => {
      ativo = false;
      fechar();
    };
  }, [clienteId, conversaId]);

  const postar = useCallback(
    async (mensagem: MensagemNaTela) => {
      if (!conversaId) return;
      try {
        const resposta = await enviarMensagem(clienteId, conversaId, {
          message_id: mensagem.id,
          conteudo: mensagem.conteudo,
        });
        // A API devolve o texto já mascarado (cartão, CPF, senha): é ele que fica na tela.
        despachar({ tipo: "confirmada", id: mensagem.id, conteudo: resposta.conteudo ?? mensagem.conteudo });
        aoAtualizarAtual.current?.();
      } catch (erro) {
        despachar({ tipo: "recusada", id: mensagem.id, erro: mensagemDeErro(erro) });
        throw erro;
      }
    },
    [clienteId, conversaId],
  );

  const pronta = estado.historicoCarregado && estado.conexao === "aberta";

  // A primeira mensagem já aparece na tela desde o início; o POST espera o stream abrir
  // para nenhum token se perder.
  const inicialPendente = useRef(estado.mensagens.find((m) => m.pendente) ?? null);
  useEffect(() => {
    const inicial = inicialPendente.current;
    if (!inicial || !pronta) return;
    inicialPendente.current = null;
    postar(inicial).catch(() => undefined);
  }, [pronta, postar]);

  const enviar = useCallback(
    async (conteudo: string) => {
      const mensagem = mensagemDoCliente(conteudo);
      despachar({ tipo: "enviada", mensagem });
      await postar(mensagem);
    },
    [postar],
  );

  const dispensarErro = useCallback(() => despachar({ tipo: "dispensar_erro" }), []);

  const ocupada = estado.aguardando || estado.emConstrucao !== null || estado.acaoAtual !== null;

  return { ...estado, pronta, ocupada, enviar, dispensarErro };
}
