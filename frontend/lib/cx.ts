/** Junta classes do Tailwind ignorando as falsas: `cx("a", ativo && "b")`. */
export function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
