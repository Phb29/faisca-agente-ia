import { Central } from "@/components/atendente/Central";

/** O login é do app inteiro (o middleware e o BFF cuidam dele): aqui não há porta própria. */
export default function PaginaDoAtendente() {
  return <Central />;
}
