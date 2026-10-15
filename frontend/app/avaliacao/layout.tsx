import type { Metadata } from "next";

export const metadata: Metadata = { title: "Avaliação" };

export default function LayoutDaAvaliacao({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
