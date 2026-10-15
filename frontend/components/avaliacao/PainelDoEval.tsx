"use client";

import { Inbox, RefreshCw } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { lerExecucao, listarExecucoes, mensagemDeErro, type Caso, type Execucao, type NomeDoEval } from "@/lib/api";
import { TEXTOS } from "@/lib/avaliacao";
import { terminada, useAmostraAoVivo } from "@/hooks/useAmostraAoVivo";
import { useRecurso } from "@/hooks/useRecurso";
import { Aviso } from "@/components/ui/Aviso";
import { Vazio } from "@/components/ui/Vazio";
import { AbaAgente } from "./AbaAgente";
import { AbaBusca } from "./AbaBusca";
import { AbaJuiz } from "./AbaJuiz";
import { CabecalhoDaAba, type EstadoDoBotao } from "./CabecalhoDaAba";
import { FaixaAoVivo } from "./FaixaAoVivo";
import { GavetaDoCaso } from "./GavetaDoCaso";
import { Numeros } from "./Numeros";

type Props = {
  nome: NomeDoEval;
  token: string;
  /** A amostra em andamento, de qualquer eval, vinda da sondagem da casca. */
  amostraGlobal: Execucao | null;
  recarregarAmostraGlobal: () => Promise<void>;
  aoIrPara: (nome: NomeDoEval) => void;
  aoFalhar: (erro: unknown) => void;
};

/** Uma aba inteira: cabeçalho, faixa ao vivo, a execução escolhida e a gaveta de detalhe. */
export function PainelDoEval({ nome, token, amostraGlobal, recarregarAmostraGlobal, aoIrPara, aoFalhar }: Props) {
  const execucoes = useRecurso(`execucoes:${nome}:${token}`, () => listarExecucoes(token, nome), {
    aoErro: aoFalhar,
  });
  const [escolhida, setEscolhida] = useState<string | null>(null);
  const padrao =
    execucoes.dados?.find((e) => e.modo === "completa" && e.status === "concluida")?.id ?? null;
  const selecionadaId = escolhida ?? padrao;
  const execucao = useRecurso(
    selecionadaId ? `execucao:${selecionadaId}` : null,
    () => lerExecucao(token, selecionadaId ?? ""),
    { aoErro: aoFalhar },
  );
  const [casoAberto, setCasoAberto] = useState<Caso | null>(null);

  const recarregarExecucoes = execucoes.recarregar;
  const aoVivo = useAmostraAoVivo(token, nome, {
    aoTerminar: () => {
      void recarregarExecucoes();
      void recarregarAmostraGlobal();
    },
    aoOcupadaPorOutro: () => void recarregarAmostraGlobal(),
    aoFalhar,
  });

  // Quem abre a aba no meio de uma amostra deste eval se conecta a ela.
  const { conectar } = aoVivo;
  const conectadaId = aoVivo.estado?.execucaoId;
  useEffect(() => {
    if (amostraGlobal?.eval === nome && amostraGlobal.id !== conectadaId) conectar(amostraGlobal.id);
  }, [amostraGlobal, nome, conectadaId, conectar]);

  const estado = aoVivo.estado;
  const ocupadaPor = amostraGlobal && amostraGlobal.eval !== nome ? amostraGlobal.eval : null;
  const ativa = estado !== null && !terminada(estado.status);
  const botao: EstadoDoBotao = ocupadaPor
    ? { tipo: "ocupado", por: ocupadaPor }
    : aoVivo.disparando || ativa
      ? {
          tipo: "rodando",
          prontos: estado?.cartoes.filter((c) => c.estado === "pronto").length ?? 0,
          disparando: aoVivo.disparando,
          naFila: estado?.status === "pendente",
        }
      : { tipo: "livre", depoisDeUma: estado !== null };

  const mostrada = execucao.dados?.id === selecionadaId ? execucao.dados : null;
  let conteudo: ReactNode;
  if (execucoes.erro && execucoes.dados === null) {
    conteudo = (
      <ErroDeCarga
        mensagem="Não foi possível carregar as execuções."
        erro={execucoes.erro}
        aoRecarregar={execucoes.recarregar}
      />
    );
  } else if (selecionadaId && execucao.erro && !mostrada) {
    conteudo = (
      <ErroDeCarga
        mensagem="Não foi possível carregar esta execução."
        erro={execucao.erro}
        aoRecarregar={execucao.recarregar}
      />
    );
  } else if (execucoes.dados === null || (selecionadaId && !mostrada)) {
    conteudo = <Numeros itens={null} />;
  } else if (!mostrada) {
    conteudo = <SemExecucao nome={nome} />;
  } else if (nome === "rag") {
    conteudo = <AbaBusca execucao={mostrada} aoAbrirCaso={setCasoAberto} />;
  } else if (nome === "agente") {
    conteudo = <AbaAgente execucao={mostrada} aoAbrirCaso={setCasoAberto} />;
  } else {
    conteudo = <AbaJuiz execucao={mostrada} aoAbrirCaso={setCasoAberto} />;
  }

  return (
    <>
      <CabecalhoDaAba
        nome={nome}
        execucoes={execucoes.dados}
        mostrada={mostrada}
        selecionadaId={selecionadaId}
        aoEscolher={setEscolhida}
        botao={botao}
        aoDisparar={() => void aoVivo.disparar()}
        aoIrPara={aoIrPara}
      />
      {estado && (
        <FaixaAoVivo nome={nome} estado={estado} aoAbrirCaso={setCasoAberto} aoDispensar={aoVivo.dispensar} />
      )}
      {conteudo}
      <GavetaDoCaso nome={nome} caso={casoAberto} aoFechar={() => setCasoAberto(null)} />
    </>
  );
}

function ErroDeCarga({
  mensagem,
  erro,
  aoRecarregar,
}: {
  mensagem: string;
  erro: unknown;
  aoRecarregar: () => Promise<void>;
}) {
  return (
    <Aviso
      acao={
        <button
          type="button"
          onClick={() => void aoRecarregar()}
          className="inline-flex items-center gap-1 font-medium underline-offset-2 hover:underline"
        >
          <RefreshCw aria-hidden className="size-3.5" /> Tentar de novo
        </button>
      }
    >
      {mensagem} {mensagemDeErro(erro)}
    </Aviso>
  );
}

function SemExecucao({ nome }: { nome: NomeDoEval }) {
  return (
    <div className="rounded-2xl bg-surface shadow-suave ring-1 ring-line">
      <Vazio icone={Inbox} titulo="Nenhuma execução completa ainda">
        Rode no terminal, antes da aula:
        <code className="mt-2 block rounded-lg bg-noite px-3 py-2 font-mono text-[12px] break-words text-noite-texto">
          {TEXTOS[nome].comando}
        </code>
      </Vazio>
    </div>
  );
}
