import {
  Banknote,
  BookOpenText,
  Brain,
  Headset,
  LifeBuoy,
  PackageSearch,
  PenLine,
  Route,
  Save,
  Search,
  ShieldCheck,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import type { NoDoGrafo, NomeDaAcao } from "@/lib/api";

export const ICONE_DA_ACAO: Record<NomeDaAcao, LucideIcon> = {
  consultar_pedido: PackageSearch,
  consultar_base_de_conhecimento: BookOpenText,
  emitir_reembolso: Banknote,
  abrir_ticket: LifeBuoy,
};

export const ICONE_DO_NO: Record<NoDoGrafo, LucideIcon> = {
  carregar_memoria: Brain,
  guardrail_entrada: ShieldCheck,
  roteador: Route,
  recuperar_contexto: Search,
  gerar_resposta: PenLine,
  agente: Workflow,
  guardrail_saida: ShieldCheck,
  escalar: Headset,
  salvar_memoria: Save,
};

export const iconeDaAcao = (nome: string): LucideIcon =>
  ICONE_DA_ACAO[nome as NomeDaAcao] ?? Workflow;

export const iconeDoNo = (no: string): LucideIcon => ICONE_DO_NO[no as NoDoGrafo] ?? Workflow;
