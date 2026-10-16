"use client";

import { Eye, EyeOff, LockKeyhole, Mail } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { destinoSeguro } from "@/lib/acesso";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { Marca } from "@/components/ui/Marca";

const CAMPO =
  "h-11 w-full rounded-xl bg-surface-2 pl-10 text-[14.5px] ring-1 ring-line transition outline-none ring-inset placeholder:text-muted focus:bg-surface focus:ring-[1.5px] focus:ring-ink/40";
const ICONE_DO_CAMPO = "pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted";

/** O `detail` de um erro da api, quando vier em texto. */
async function detalheDe(resposta: Response): Promise<string | null> {
  try {
    const corpo = (await resposta.json()) as { detail?: unknown };
    return typeof corpo.detail === "string" ? corpo.detail : null;
  } catch {
    return null;
  }
}

/**
 * Login da equipe. O e-mail e a senha vão para o BFF, que fala com a api e guarda a sessão
 * num cookie HttpOnly; depois, volta para onde a pessoa estava (`proximo`).
 */
export function FormularioDeLogin() {
  const parametros = useSearchParams();
  const destino = destinoSeguro(parametros.get("proximo"));
  const sessaoVencida = parametros.get("motivo") === "sessao";

  const idDoEmail = useId();
  const idDaSenha = useId();
  const campoDaSenha = useRef<HTMLInputElement>(null);
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [senhaVisivel, setSenhaVisivel] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // Quem já tem sessão segue direto. Acontece com link aberto de outro site: por causa do
  // SameSite=Strict, essa primeira visita chega sem o cookie, mas esta conferência já o leva.
  useEffect(() => {
    let ativo = true;
    fetch("/api/acesso/eu", { cache: "no-store" })
      .then((resposta) => {
        if (ativo && resposta.ok) window.location.replace(destino);
      })
      .catch(() => undefined);
    return () => {
      ativo = false;
    };
  }, [destino]);

  async function entrar(evento: FormEvent) {
    evento.preventDefault();
    if (enviando) return;
    setEnviando(true);
    setErro(null);
    try {
      const resposta = await fetch("/api/acesso/entrar", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ email: email.trim(), senha }),
        cache: "no-store",
      });
      if (resposta.ok) {
        // O botão segue travado até a próxima página carregar.
        window.location.replace(destino);
        return;
      }
      if (resposta.status === 429) {
        setErro((await detalheDe(resposta)) ?? "Muitas tentativas. Tente de novo em alguns minutos.");
      } else if (resposta.status === 401 || resposta.status === 422) {
        // A mesma mensagem para e-mail e senha errados: não revela qual dos dois falhou.
        setErro("E-mail ou senha incorretos.");
        setSenha("");
        campoDaSenha.current?.focus();
      } else {
        setErro("Não foi possível entrar agora. Tente de novo em instantes.");
      }
    } catch {
      setErro("Não foi possível falar com o servidor. Confira a conexão.");
    }
    setEnviando(false);
  }

  const aviso = erro ?? (sessaoVencida ? "Sua sessão terminou. Entre de novo para continuar." : null);

  return (
    <div className="grid min-h-dvh place-items-center px-5 py-12">
      <div className="w-full max-w-[400px]">
        {/* method="post": sem JavaScript, a senha nunca vai parar na URL. */}
        <form
          method="post"
          onSubmit={entrar}
          className="animate-surgir rounded-3xl bg-surface p-8 shadow-flutuante ring-1 ring-line"
        >
          <Marca tamanho="lg" />
          <p className="sobretitulo mt-6">Suporte Ampère</p>
          <h1 className="mt-2 font-display text-[30px] leading-[1.1] font-semibold tracking-[-0.03em]">Entrar</h1>
          <p className="mt-2 text-[14.5px] leading-relaxed text-muted">
            O chat, a Central do Atendente e a Avaliação ficam atrás deste login.
          </p>

          {aviso && <Aviso className="mt-5">{aviso}</Aviso>}

          <label htmlFor={idDoEmail} className="mt-6 block text-[12.5px] font-medium text-ink-2">
            E-mail
          </label>
          <div className="relative mt-1.5">
            <Mail aria-hidden className={ICONE_DO_CAMPO} strokeWidth={1.7} />
            <input
              id={idDoEmail}
              name="email"
              type="email"
              inputMode="email"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              required
              autoFocus
              value={email}
              onChange={(evento) => setEmail(evento.target.value)}
              className={`${CAMPO} pr-3`}
              placeholder="voce@empresa.com.br"
            />
          </div>

          <label htmlFor={idDaSenha} className="mt-4 block text-[12.5px] font-medium text-ink-2">
            Senha
          </label>
          <div className="relative mt-1.5">
            <LockKeyhole aria-hidden className={ICONE_DO_CAMPO} strokeWidth={1.7} />
            <input
              ref={campoDaSenha}
              id={idDaSenha}
              name="senha"
              type={senhaVisivel ? "text" : "password"}
              autoComplete="current-password"
              required
              value={senha}
              onChange={(evento) => setSenha(evento.target.value)}
              className={`${CAMPO} pr-11`}
              placeholder="••••••••••"
            />
            <button
              type="button"
              onClick={() => setSenhaVisivel((atual) => !atual)}
              aria-label={senhaVisivel ? "Esconder a senha" : "Mostrar a senha"}
              aria-pressed={senhaVisivel}
              aria-controls={idDaSenha}
              className="absolute top-1/2 right-1.5 inline-flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted transition-colors hover:bg-canvas-2 hover:text-ink"
            >
              {senhaVisivel ? (
                <EyeOff aria-hidden className="size-4" strokeWidth={1.7} />
              ) : (
                <Eye aria-hidden className="size-4" strokeWidth={1.7} />
              )}
            </button>
          </div>

          <Botao
            type="submit"
            variante="volt"
            tamanho="lg"
            className="mt-6 w-full"
            carregando={enviando}
            disabled={!email.trim() || !senha}
          >
            Entrar
          </Botao>
        </form>

        <p className="mt-6 text-center text-[12.5px] text-muted">Acesso restrito à equipe da Ampère.</p>
      </div>
    </div>
  );
}
