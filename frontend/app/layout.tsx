import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Suporte Ampère",
  description: "Chatbot de suporte ao Cliente da Ampère Eletrônicos",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body className="flex min-h-screen flex-col antialiased">
        <header className="border-b border-stone-200 bg-white">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
            <Link href="/" className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-400 font-bold text-stone-900">
                A
              </span>
              <span className="text-lg font-semibold tracking-tight">
                Suporte Ampère
              </span>
            </Link>
            <nav className="flex items-center gap-4 text-sm">
              <Link href="/" className="text-stone-600 hover:text-stone-900">
                Chat
              </Link>
              <Link
                href="/atendente"
                className="text-stone-600 hover:text-stone-900"
              >
                Tela do Atendente
              </Link>
            </nav>
          </div>
        </header>
        <main className="flex flex-1 flex-col">{children}</main>
      </body>
    </html>
  );
}
