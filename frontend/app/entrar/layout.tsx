import type { Metadata } from "next";

export const metadata: Metadata = { title: "Entrar" };

export default function LayoutDaEntrada({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
