import type { Metadata } from "next";

export const metadata: Metadata = { title: "Central do Atendente" };

export default function LayoutDoAtendente({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
