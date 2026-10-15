// Formatação para a tela, sempre em pt-BR.

const reais = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const hora = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" });
const horaComSegundos = new Intl.DateTimeFormat("pt-BR", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});
const diaEMes = new Intl.DateTimeFormat("pt-BR", { day: "numeric", month: "short" });
const diaMesEAno = new Intl.DateTimeFormat("pt-BR", {
  day: "numeric",
  month: "short",
  year: "numeric",
});
const dataPorExtenso = new Intl.DateTimeFormat("pt-BR", {
  weekday: "long",
  day: "numeric",
  month: "long",
});

function paraData(iso: string): Date | null {
  const data = new Date(iso);
  return Number.isNaN(data.getTime()) ? null : data;
}

function mesmoDia(a: Date, b: Date): boolean {
  return a.toDateString() === b.toDateString();
}

export const formatarReais = (valor: number) => reais.format(valor);

export const formatarPorcentagem = (probabilidade: number) =>
  `${Math.round(probabilidade * 100)}%`;

export function formatarHora(iso: string, { segundos = false } = {}): string {
  const data = paraData(iso);
  if (!data) return "";
  return (segundos ? horaComSegundos : hora).format(data);
}

/** "14:32" se for hoje, "12 de set., 14:32" nos outros dias. */
export function formatarMomento(iso: string): string {
  const data = paraData(iso);
  if (!data) return iso;
  if (mesmoDia(data, new Date())) return hora.format(data);
  return `${diaEMes.format(data)}, ${hora.format(data)}`;
}

/** Data de calendário ("2026-08-12") sem passar por fuso horário. */
export function formatarDiaDoCalendario(dia: string): string {
  const [ano, mes, diaDoMes] = dia.split("-").map(Number);
  if (!ano || !mes || !diaDoMes) return dia;
  return diaMesEAno.format(new Date(ano, mes - 1, diaDoMes));
}

export const formatarHoje = () => dataPorExtenso.format(new Date());

/** "agora", "há 4 min", "há 2 h", "ontem", "12 de set." */
export function formatarRelativo(iso: string, agora: Date = new Date()): string {
  const data = paraData(iso);
  if (!data) return iso;
  const segundos = Math.max(0, (agora.getTime() - data.getTime()) / 1000);
  if (segundos < 45) return "agora";
  if (segundos < 3600) return `há ${Math.round(segundos / 60)} min`;
  if (mesmoDia(data, agora)) return `há ${Math.round(segundos / 3600)} h`;
  const ontem = new Date(agora);
  ontem.setDate(agora.getDate() - 1);
  if (mesmoDia(data, ontem)) return "ontem";
  return diaEMes.format(data);
}

export type Periodo = "Hoje" | "Últimos 7 dias" | "Anteriores";

export function periodoDe(iso: string, agora: Date = new Date()): Periodo {
  const data = paraData(iso);
  if (!data || mesmoDia(data, agora)) return "Hoje";
  const dias = (agora.getTime() - data.getTime()) / 86_400_000;
  return dias <= 7 ? "Últimos 7 dias" : "Anteriores";
}

export function iniciais(nome: string): string {
  const partes = nome.trim().split(/\s+/).filter(Boolean);
  if (partes.length === 0) return "?";
  const primeira = partes[0][0] ?? "";
  const ultima = partes.length > 1 ? (partes[partes.length - 1][0] ?? "") : "";
  return (primeira + ultima).toUpperCase();
}

export const primeiroNome = (nome: string) => nome.trim().split(/\s+/)[0] ?? nome;
