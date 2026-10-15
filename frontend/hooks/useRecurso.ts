"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Opcoes = {
  /** Recarrega sozinho a cada N ms enquanto a aba estiver visível (sondagem). */
  intervaloMs?: number;
  aoErro?: (erro: unknown) => void;
};

type Estado<T> = { chave: string | null; dados: T | null; erro: unknown; carregando: boolean };

/**
 * Busca um recurso da API identificado por `chave`. Trocar a chave descarta os dados da
 * anterior; `chave` nula não busca nada. `buscar` pode mudar a cada render.
 */
export function useRecurso<T>(chave: string | null, buscar: () => Promise<T>, opcoes: Opcoes = {}) {
  const { intervaloMs, aoErro } = opcoes;
  const [estado, setEstado] = useState<Estado<T>>({
    chave: null,
    dados: null,
    erro: null,
    carregando: false,
  });

  const buscarAtual = useRef(buscar);
  const aoErroAtual = useRef(aoErro);
  useEffect(() => {
    buscarAtual.current = buscar;
    aoErroAtual.current = aoErro;
  });

  const recarregar = useCallback(async () => {
    if (chave === null) return;
    setEstado((atual) =>
      atual.chave === chave
        ? { ...atual, carregando: true }
        : { chave, dados: null, erro: null, carregando: true },
    );
    try {
      const dados = await buscarAtual.current();
      setEstado((atual) =>
        atual.chave === chave ? { chave, dados, erro: null, carregando: false } : atual,
      );
    } catch (erro) {
      setEstado((atual) => (atual.chave === chave ? { ...atual, erro, carregando: false } : atual));
      aoErroAtual.current?.(erro);
    }
  }, [chave]);

  useEffect(() => {
    void recarregar();
    if (!intervaloMs) return;
    // Aba oculta não consulta a API; ao voltar, atualiza na hora em vez de esperar o relógio.
    const seVisivel = () => {
      if (document.visibilityState === "visible") void recarregar();
    };
    const relogio = setInterval(seVisivel, intervaloMs);
    document.addEventListener("visibilitychange", seVisivel);
    return () => {
      clearInterval(relogio);
      document.removeEventListener("visibilitychange", seVisivel);
    };
  }, [recarregar, intervaloMs]);

  const daChave = estado.chave === chave;
  return {
    dados: daChave ? estado.dados : null,
    erro: daChave ? estado.erro : null,
    carregando: chave !== null && (!daChave || estado.carregando),
    recarregar,
  };
}
