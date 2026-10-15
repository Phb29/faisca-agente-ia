// Todo rótulo que a tela mostra para um valor da API, num lugar só, em pt-BR.
// O `tom` escolhe a cor semântica (ver components/ui/tons.ts); nenhuma regra de domínio aqui.

import type {
  Categoria,
  Linha,
  MotivoDoGate,
  NoDoGrafo,
  NomeDaAcao,
  Prioridade,
  StatusDaConversa,
  StatusDoPedido,
} from "./api";

export type Tom = "neutro" | "sucesso" | "alerta" | "perigo" | "info" | "volt";
export type RotuloComTom = { rotulo: string; tom: Tom };

function comPadrao<V>(mapa: Record<string, V>, padrao: (chave: string) => V) {
  return (chave: string): V => mapa[chave] ?? padrao(chave);
}

const semTom = (chave: string): RotuloComTom => ({ rotulo: chave, tom: "neutro" });

export const statusDaConversa = comPadrao<RotuloComTom>(
  {
    aberta: { rotulo: "Aberta", tom: "neutro" },
    aprovacao_pendente: { rotulo: "Aprovação pendente", tom: "alerta" },
    escalada: { rotulo: "Escalada", tom: "info" },
    resolvida: { rotulo: "Resolvida", tom: "sucesso" },
  } satisfies Record<StatusDaConversa, RotuloComTom>,
  semTom,
);

export const statusDoPedido = comPadrao<RotuloComTom>(
  {
    entregue: { rotulo: "Entregue", tom: "sucesso" },
    em_transporte: { rotulo: "Em transporte", tom: "info" },
    aguardando_pagamento: { rotulo: "Aguardando pagamento", tom: "alerta" },
    devolvido: { rotulo: "Devolvido", tom: "neutro" },
    cancelado: { rotulo: "Cancelado", tom: "perigo" },
  } satisfies Record<StatusDoPedido, RotuloComTom>,
  semTom,
);

export const linha = comPadrao<string>(
  {
    notebooks: "Notebooks",
    celulares: "Celulares",
    acessorios: "Acessórios",
  } satisfies Record<Linha, string>,
  (chave) => chave,
);

export type RotuloDeAcao = { rotulo: string; andamento: string };

export const acao = comPadrao<RotuloDeAcao>(
  {
    consultar_pedido: { rotulo: "Consultar Pedido", andamento: "Consultando o Pedido" },
    consultar_base_de_conhecimento: {
      rotulo: "Consultar políticas",
      andamento: "Buscando nas políticas da Loja",
    },
    emitir_reembolso: { rotulo: "Emitir Reembolso", andamento: "Processando o Reembolso" },
    abrir_ticket: { rotulo: "Abrir Ticket", andamento: "Abrindo um Ticket para um Atendente" },
  } satisfies Record<NomeDaAcao, RotuloDeAcao>,
  (chave) => ({ rotulo: chave, andamento: `Executando ${chave}` }),
);

export type RotuloDeNo = { rotulo: string; descricao: string };

export const noDoGrafo = comPadrao<RotuloDeNo>(
  {
    carregar_memoria: {
      rotulo: "Memória carregada",
      descricao: "Fatos, Conversas anteriores e instruções do Cliente",
    },
    guardrail_entrada: {
      rotulo: "Guardrail de entrada",
      descricao: "Manipulação, fora de escopo e dado sensível",
    },
    roteador: { rotulo: "Roteador", descricao: "Qual caminho a mensagem segue" },
    recuperar_contexto: {
      rotulo: "Busca na Base de Conhecimento",
      descricao: "Busca híbrida nas políticas da Loja",
    },
    gerar_resposta: { rotulo: "Resposta escrita", descricao: "Gerador com os trechos das políticas" },
    agente: { rotulo: "Agente", descricao: "Gerador com as quatro Ações" },
    guardrail_saida: {
      rotulo: "Guardrail de saída",
      descricao: "Fora do contexto, promessa indevida e vazamento",
    },
    escalar: { rotulo: "Escalada", descricao: "Ticket aberto para um Atendente" },
    salvar_memoria: { rotulo: "Memória salva", descricao: "Fatos e episódio desta Conversa" },
  } satisfies Record<NoDoGrafo, RotuloDeNo>,
  (chave) => ({ rotulo: chave, descricao: "" }),
);

export const motivoDoGate = comPadrao<string>(
  {
    valor_acima_do_limite: "Valor acima do limite",
    reembolso_recente: "Reembolso recente",
    gate: "Decisão do Jev",
  } satisfies Record<MotivoDoGate, string>,
  (chave) => chave,
);

export type RotuloDePrioridade = RotuloComTom & { nivel: 1 | 2 | 3 };

export const prioridade = comPadrao<RotuloDePrioridade>(
  {
    baixa: { rotulo: "Baixa", tom: "neutro", nivel: 1 },
    media: { rotulo: "Média", tom: "alerta", nivel: 2 },
    alta: { rotulo: "Alta", tom: "perigo", nivel: 3 },
  } satisfies Record<Prioridade, RotuloDePrioridade>,
  (chave) => ({ rotulo: chave, tom: "neutro", nivel: 1 }),
);

export const categoria = comPadrao<string>(
  {
    troca: "Troca",
    devolucao: "Devolução",
    frete: "Frete",
    garantia: "Garantia",
    pagamento: "Pagamento",
    cadastro: "Cadastro",
    reembolso: "Reembolso",
    outro: "Outro",
  } satisfies Record<Categoria, string>,
  (chave) => chave,
);
