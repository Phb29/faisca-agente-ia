/** Id único gerado no navegador (o `message_id` que torna o envio idempotente). */
export function gerarId(prefixo = ""): string {
  const uuid =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `${prefixo}${uuid}`;
}
