"use client";

import { Check, ChevronDown, NotebookPen, Plus, Undo2 } from "lucide-react";
import { useId, useState } from "react";
import { lerMemoriaProcedural, listarClientes, salvarMemoriaProcedural } from "@/lib/api";
import { Botao } from "@/components/ui/Botao";
import { Ponto } from "@/components/ui/Pilula";
import { Esqueleto } from "@/components/ui/Vazio";
import { useRecurso } from "@/hooks/useRecurso";

const EXEMPLOS = [
  "Responder em tom formal.",
  "Não oferecer cupom de desconto.",
  "Tratar o Cliente pelo primeiro nome.",
  "Confirmar o Pedido antes de agir.",
];

type Props = {
  token: string;
  aoSalvar: (mensagem: string) => void;
  aoErro: (erro: unknown) => void;
};

/** Instruções livres por Cliente que o chatbot recebe no system prompt de toda Conversa. */
export function EditorDeMemoria({ token, aoSalvar, aoErro }: Props) {
  const idDoCliente = useId();
  const idDoTexto = useId();
  const clientes = useRecurso("clientes", listarClientes, { aoErro });
  const [escolhido, setEscolhido] = useState<string | null>(null);
  const clienteId = escolhido ?? clientes.dados?.[0]?.id ?? null;

  const memoria = useRecurso(
    clienteId ? `memoria:${clienteId}` : null,
    () => lerMemoriaProcedural(token, clienteId ?? ""),
    { aoErro },
  );
  // Rascunho por Cliente: trocar de Cliente não perde o que foi escrito no outro.
  const [rascunhos, setRascunhos] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState(false);
  const [salvoAgora, setSalvoAgora] = useState<string | null>(null);

  const salvo = memoria.dados?.texto ?? "";
  const texto = clienteId ? (rascunhos[clienteId] ?? salvo) : "";
  const alterado = clienteId !== null && rascunhos[clienteId] !== undefined && rascunhos[clienteId] !== salvo;
  const carregando = memoria.dados === null;

  function editar(novo: string) {
    if (!clienteId) return;
    setRascunhos((atuais) => ({ ...atuais, [clienteId]: novo }));
    setSalvoAgora(null);
  }

  function descartar() {
    if (!clienteId) return;
    setRascunhos((atuais) => {
      const restantes = { ...atuais };
      delete restantes[clienteId];
      return restantes;
    });
  }

  async function salvar() {
    if (!clienteId) return;
    setSalvando(true);
    try {
      await salvarMemoriaProcedural(token, clienteId, texto);
      await memoria.recarregar();
      descartar();
      setSalvoAgora(clienteId);
      const nome = clientes.dados?.find((c) => c.id === clienteId)?.nome ?? clienteId;
      aoSalvar(`Memória Procedural de ${nome} salva. Vale a partir da próxima mensagem.`);
    } catch (erro) {
      aoErro(erro);
    } finally {
      setSalvando(false);
    }
  }

  return (
    <section aria-labelledby="titulo-memoria" className="overflow-hidden rounded-2xl bg-surface shadow-suave ring-1 ring-line">
      <div className="p-5 sm:p-6">
        <div className="flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-xl bg-noite text-volt">
            <NotebookPen aria-hidden className="size-4" strokeWidth={1.8} />
          </span>
          <div>
            <h2 id="titulo-memoria" className="text-[15px] font-semibold tracking-[-0.01em]">
              Memória Procedural
            </h2>
            <p className="text-[12.5px] text-muted">Como o chatbot deve atender cada Cliente.</p>
          </div>
        </div>

        <label htmlFor={idDoCliente} className="mt-6 block text-[12.5px] font-medium text-ink-2">
          Cliente
        </label>
        <div className="relative mt-1.5">
          <select
            id={idDoCliente}
            value={clienteId ?? ""}
            onChange={(evento) => setEscolhido(evento.target.value)}
            disabled={!clientes.dados}
            className="h-10 w-full appearance-none rounded-xl bg-surface-2 pr-9 pl-3 text-[13.5px] ring-1 ring-line outline-none ring-inset focus:ring-[1.5px] focus:ring-ink/40"
          >
            {!clientes.dados && <option value="">Carregando Clientes…</option>}
            {clientes.dados?.map((cliente) => (
              <option key={cliente.id} value={cliente.id}>
                {cliente.nome} · {cliente.id}
              </option>
            ))}
          </select>
          <ChevronDown
            aria-hidden
            className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted"
          />
        </div>

        <label htmlFor={idDoTexto} className="mt-5 block text-[12.5px] font-medium text-ink-2">
          Instruções
        </label>
        {carregando ? (
          <Esqueleto className="mt-1.5 h-[168px] rounded-xl" />
        ) : (
          <textarea
            id={idDoTexto}
            value={texto}
            onChange={(evento) => editar(evento.target.value)}
            rows={7}
            placeholder="Sem instruções para este Cliente. O chatbot segue o padrão da Loja."
            className="mt-1.5 w-full resize-y rounded-xl bg-surface-2 px-3.5 py-3 text-[13.5px] leading-relaxed ring-1 ring-line outline-none ring-inset placeholder:text-muted focus:bg-surface focus:ring-[1.5px] focus:ring-ink/40"
          />
        )}

        <p className="mt-4 sobretitulo">Sugestões</p>
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {EXEMPLOS.map((exemplo) => (
            <li key={exemplo}>
              <button
                type="button"
                disabled={carregando}
                onClick={() => editar(texto.trim() ? `${texto.trimEnd()}\n${exemplo}` : exemplo)}
                className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2.5 py-1 text-[12px] text-ink-2 ring-1 ring-line transition-colors ring-inset hover:bg-canvas-2 hover:text-ink disabled:opacity-50"
              >
                <Plus aria-hidden className="size-3" /> {exemplo}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-line bg-surface-2 px-5 py-3.5 sm:px-6">
        <span className="flex items-center gap-2 text-[12px] text-muted" aria-live="polite">
          {alterado ? (
            <>
              <Ponto tom="alerta" /> Alterações não salvas
            </>
          ) : salvoAgora === clienteId && clienteId ? (
            <>
              <Check aria-hidden className="size-3.5 text-sucesso" /> Salvo
            </>
          ) : (
            <span className="font-mono text-[11px]">{texto.length} caracteres</span>
          )}
        </span>
        <span className="flex gap-1.5">
          {alterado && (
            <Botao variante="fantasma" tamanho="sm" icone={Undo2} onClick={descartar} disabled={salvando}>
              Descartar
            </Botao>
          )}
          <Botao tamanho="sm" onClick={() => void salvar()} carregando={salvando} disabled={!alterado}>
            Salvar
          </Botao>
        </span>
      </div>
    </section>
  );
}
