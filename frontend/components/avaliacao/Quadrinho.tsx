import type { Caso, CasoAgente, Veredito } from "@/lib/api";
import { temErro } from "@/lib/avaliacao";
import { cx } from "@/lib/cx";
import { Pilula } from "@/components/ui/Pilula";

type Props = {
  /** true sim, false não, null não se aplica. */
  ok: boolean | null;
  rotulo: string;
  escuro?: boolean;
  tamanho?: "sm" | "md";
  /** Como ler o sim e o não para quem usa leitor de tela: "acertou/errou" ou "aprovou/reprovou". */
  verbos?: [string, string];
};

/** O quadradinho de uma conferência: ✓ sim, ✗ não, – não se aplica. Nunca só a cor. */
export function Quadrinho({
  ok,
  rotulo,
  escuro = false,
  tamanho = "md",
  verbos = ["acertou", "errou"],
}: Props) {
  const descricao = `${rotulo}: ${ok === null ? "não se aplica" : ok ? verbos[0] : verbos[1]}`;
  return (
    <span
      role="img"
      aria-label={descricao}
      title={descricao}
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-md font-semibold",
        tamanho === "sm" ? "size-5 text-[11px]" : "size-6 text-[12px]",
        ok === false && "bg-perigo text-white",
        ok === true && (escuro ? "bg-volt/15 text-volt" : "bg-sucesso-soft text-sucesso"),
        ok === null &&
          (escuro ? "bg-noite-line text-noite-muted" : "bg-surface-2 text-muted ring-1 ring-line ring-inset"),
      )}
    >
      {ok === null ? "–" : ok ? "✓" : "✗"}
    </span>
  );
}

/** As três conferências esperado-contra-obtido de um cenário do agente: usadas aqui e na gaveta de detalhe. */
export const CONFERENCIAS = [
  ["intencao", "Intenção"],
  ["acao", "Ação"],
  ["desfecho", "Desfecho"],
] as const;

/** Os quatro quadradinhos de um cenário do agente: intenção, Ação, desfecho e juiz. */
export function QuadrinhosDoAgente({ caso, escuro = false }: { caso: Caso; escuro?: boolean }) {
  if (temErro(caso)) return <Pilula tom="perigo">falhou</Pilula>;
  const c = caso as CasoAgente;
  return (
    <span className="flex shrink-0 gap-1.5">
      {CONFERENCIAS.map(([chave, rotulo]) => (
        <Quadrinho key={chave} ok={c.ok[chave]} rotulo={rotulo} escuro={escuro} />
      ))}
      <Quadrinho ok={c.juiz ? c.juiz.aprovada : null} rotulo="Juiz" escuro={escuro} />
    </span>
  );
}

/** Um veredito com a crítica: o humano, o juiz, a fidelidade ou a relevância. Feito só de
 * `span` porque também aparece dentro de botões (que só aceitam conteúdo de frase). */
export function Voz({ quem, veredito }: { quem: string; veredito: Veredito }) {
  return (
    <span className="block rounded-xl bg-surface-2 p-3 text-[13px] leading-relaxed text-ink-2 ring-1 ring-line ring-inset">
      <span className="mb-1.5 flex items-center gap-2 font-mono text-[10.5px] tracking-[0.08em] text-muted uppercase">
        <Quadrinho ok={veredito.aprovada} rotulo={quem} tamanho="sm" verbos={["aprovou", "reprovou"]} />
        {quem} · {veredito.aprovada ? "Aprovada" : "Reprovada"}
      </span>
      {veredito.critica}
    </span>
  );
}
