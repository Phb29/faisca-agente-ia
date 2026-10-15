"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";
import { apagar, assinar, gravar, lerBruto } from "@/lib/armazenamento";

/**
 * Um valor JSON no localStorage como estado React. `hidratado` é falso no servidor e no
 * primeiro render do navegador, para a página não piscar um estado errado.
 */
export function useArmazenado<T>(chave: string) {
  const bruto = useSyncExternalStore(
    assinar,
    () => lerBruto(chave),
    () => undefined,
  );

  const valor = useMemo<T | null>(() => {
    if (!bruto) return null;
    try {
      return JSON.parse(bruto) as T;
    } catch {
      return null;
    }
  }, [bruto]);

  const definir = useCallback(
    (novo: T | null) => (novo === null ? apagar(chave) : gravar(chave, novo)),
    [chave],
  );

  return { valor, hidratado: bruto !== undefined, definir };
}
