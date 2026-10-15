"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  doAtendente,
  ErroDaApi,
  lerExecucao,
  rodarAmostra,
  urlDoStreamDaExecucao,
  type AmostraOcupada,
  type Caso,
  type Execucao,
  type NomeDoEval,
  type Sorteado,
  type StatusDaExecucao,
} from "@/lib/api";
import { abrirStreamComToken, type EstadoDaConexao, type EventoBruto } from "@/lib/streamComToken";

export type EstadoDoCartao = "aguardando" | "rodando" | "pronto";
export type Cartao = Sorteado & { estado: EstadoDoCartao; fases: string[]; caso: Caso | null };

export type AoVivo = {
  execucaoId: string;
  status: StatusDaExecucao;
  cartoes: Cartao[];
  resumo: unknown;
  erro: string | null;
  conexao: EstadoDaConexao;
  /** Quando a amostra começou a rodar, para o tempo corrido. */
  iniciadaEm: string | null;
};

export const terminada = (status: StatusDaExecucao): boolean =>
  status === "concluida" || status === "erro";

function cartoesDaFoto(execucao: Execucao, anteriores: Cartao[]): Cartao[] {
  const prontos = new Map((execucao.casos ?? []).map((caso) => [caso.id, caso]));
  return (execucao.contexto.sorteados ?? []).map((sorteado) => {
    const anterior = anteriores.find((c) => c.id === sorteado.id);
    const caso = prontos.get(sorteado.id) ?? anterior?.caso ?? null;
    const estado: EstadoDoCartao = caso ? "pronto" : (anterior?.estado ?? "aguardando");
    return { ...sorteado, caso, fases: anterior?.fases ?? [], estado };
  });
}

/** Aplica um evento do stream ao estado da faixa. A foto e o evento do mesmo caso chegam às
 * vezes os dois (reconexão); como tudo é pelo id do caso, o repetido só se sobrepõe. */
export function aplicarEvento(estado: AoVivo, { tipo, dados }: EventoBruto): AoVivo {
  switch (tipo) {
    case "eval_estado": {
      const execucao = dados as Execucao;
      const cartoes = cartoesDaFoto(execucao, estado.cartoes);
      if (terminada(estado.status)) {
        // Uma releitura que chega depois do fim só completa os cartões: não reabre a amostra.
        return { ...estado, cartoes: cartoes.length > 0 ? cartoes : estado.cartoes };
      }
      return {
        ...estado,
        status: execucao.status,
        cartoes: cartoes.length > 0 ? cartoes : estado.cartoes,
        resumo: execucao.resumo ?? estado.resumo,
        erro: execucao.erro,
        iniciadaEm: execucao.iniciada_em ?? estado.iniciadaEm,
      };
    }
    case "eval_inicio": {
      const { casos } = dados as { casos: Sorteado[] };
      return {
        ...estado,
        status: "rodando",
        iniciadaEm: estado.iniciadaEm ?? new Date().toISOString(),
        cartoes: casos.map((s) => ({ ...s, estado: "aguardando", fases: [], caso: null })),
      };
    }
    case "eval_fase": {
      const { caso_id, fase } = dados as { caso_id: string; fase: string };
      return {
        ...estado,
        status: "rodando",
        cartoes: estado.cartoes.map((c) =>
          c.id === caso_id ? { ...c, estado: "rodando", fases: [...c.fases, fase] } : c,
        ),
      };
    }
    case "eval_caso": {
      const { caso } = dados as { caso?: Caso };
      if (!caso) return estado;
      return {
        ...estado,
        cartoes: estado.cartoes.map((c) => (c.id === caso.id ? { ...c, estado: "pronto", caso } : c)),
      };
    }
    case "eval_fim":
      return { ...estado, status: "concluida", resumo: (dados as { resumo: unknown }).resumo };
    case "error":
      return {
        ...estado,
        status: "erro",
        erro: (dados as { mensagem?: string }).mensagem ?? "A amostra parou.",
      };
    default:
      return estado;
  }
}

function encerraOStream({ tipo, dados }: EventoBruto): boolean {
  if (tipo === "eval_fim" || tipo === "error") return true;
  return tipo === "eval_estado" && terminada((dados as Execucao).status);
}

type Opcoes = {
  /** A amostra terminou, bem ou mal: hora de atualizar a lista de execuções. */
  aoTerminar: () => void;
  /** O botão esbarrou numa amostra de outro eval. */
  aoOcupadaPorOutro: () => void;
  aoFalhar: (erro: unknown) => void;
};

/**
 * Dispara uma amostra do eval e acompanha o stream dela, ou se conecta a uma que já roda.
 * A faixa ao vivo desenha o `estado`; `dispensar` fecha a faixa de uma amostra terminada e
 * impede que a sondagem a reabra.
 */
export function useAmostraAoVivo(token: string, nome: NomeDoEval, opcoes: Opcoes) {
  const [estado, setEstado] = useState<AoVivo | null>(null);
  const [disparando, setDisparando] = useState(false);
  const fecharStream = useRef<(() => void) | null>(null);
  const dispensadas = useRef(new Set<string>());
  // Qual execução o stream já atende: a sondagem de 5 s e o POST de `disparar` podem chegar
  // quase juntos com o mesmo id, e sem isso o segundo `conectar` reabriria o stream à toa,
  // zerando os cartões por um instante.
  const conectadaId = useRef<string | null>(null);
  const opcoesAtuais = useRef(opcoes);
  useEffect(() => {
    opcoesAtuais.current = opcoes;
  });
  // Guarda se o painel ainda está montado: `disparar` pode terminar o POST depois que o
  // presenter já trocou de aba, e aí `conectar` não deve abrir um stream que ninguém vai fechar.
  const montado = useRef(false);
  useEffect(() => {
    montado.current = true;
    return () => {
      montado.current = false;
      fecharStream.current?.();
    };
  }, []);

  const daExecucao = useCallback(
    (execucaoId: string, mudar: (atual: AoVivo) => AoVivo) =>
      setEstado((atual) => (atual?.execucaoId === execucaoId ? mudar(atual) : atual)),
    [],
  );

  const conectar = useCallback(
    (execucaoId: string) => {
      if (!montado.current || dispensadas.current.has(execucaoId)) return;
      if (conectadaId.current === execucaoId) return;
      conectadaId.current = execucaoId;
      fecharStream.current?.();
      setEstado({
        execucaoId,
        status: "pendente",
        cartoes: [],
        resumo: null,
        erro: null,
        conexao: "conectando",
        iniciadaEm: null,
      });
      fecharStream.current = abrirStreamComToken({
        url: urlDoStreamDaExecucao(execucaoId),
        cabecalhos: doAtendente(token),
        aoMudarConexao: (conexao) => daExecucao(execucaoId, (atual) => ({ ...atual, conexao })),
        aoFalhar: (erro) => {
          daExecucao(execucaoId, (atual) => ({ ...atual, status: "erro", erro: erro.message }));
          opcoesAtuais.current.aoFalhar(erro);
        },
        aoEvento: (evento) => {
          daExecucao(execucaoId, (atual) => aplicarEvento(atual, evento));
          if (evento.tipo === "eval_caso" && (evento.dados as { grande?: boolean }).grande) {
            lerExecucao(token, execucaoId).then(
              (execucao) =>
                daExecucao(execucaoId, (atual) =>
                  aplicarEvento(atual, { tipo: "eval_estado", dados: execucao }),
                ),
              (erro) => opcoesAtuais.current.aoFalhar(erro),
            );
          }
          const fim = encerraOStream(evento);
          if (fim) opcoesAtuais.current.aoTerminar();
          return fim;
        },
      });
    },
    [token, daExecucao],
  );

  const disparar = useCallback(async () => {
    setDisparando(true);
    try {
      // Uma tentativa extra: se o 409 veio sem id, a outra amostra acabou entre a recusa e a
      // releitura, e repetir o POST já deve passar.
      for (let tentativa = 0; tentativa < 2; tentativa++) {
        try {
          const { execucao_id } = await rodarAmostra(token, nome);
          conectar(execucao_id);
          return;
        } catch (erro) {
          if (!(erro instanceof ErroDaApi) || erro.status !== 409) {
            opcoesAtuais.current.aoFalhar(erro);
            return;
          }
          const ocupada = erro.corpo as AmostraOcupada | null;
          if (ocupada?.execucao_id && ocupada.eval === nome) {
            conectar(ocupada.execucao_id);
            return;
          }
          if (!ocupada?.execucao_id && tentativa === 0) continue;
          opcoesAtuais.current.aoOcupadaPorOutro();
          return;
        }
      }
    } finally {
      setDisparando(false);
    }
  }, [token, nome, conectar]);

  const dispensar = useCallback(() => {
    if (estado) dispensadas.current.add(estado.execucaoId);
    fecharStream.current?.();
    fecharStream.current = null;
    conectadaId.current = null;
    setEstado(null);
  }, [estado]);

  return { estado, disparando, conectar, disparar, dispensar };
}
