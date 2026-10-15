-- Esquema inicial: seed da Loja (clientes, pedidos, reembolsos), Conversas e mensagens,
-- fila de jobs, Aprovações Pendentes e Tickets.
-- `conversas.cliente_id` não tem FK para `clientes` de propósito: um Cliente novo, sem
-- cadastro, pode conversar.
-- `mensagens.criada_em` usa clock_timestamp() (e não now(), que é fixo dentro da transação)
-- para que duas mensagens gravadas na mesma transação fiquem em ordem.

CREATE TABLE IF NOT EXISTS migracoes (
    nome text PRIMARY KEY,
    aplicada_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS clientes (
    id text PRIMARY KEY,
    nome text NOT NULL,
    email text NOT NULL,
    criado_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pedidos (
    id text PRIMARY KEY,
    cliente_id text NOT NULL REFERENCES clientes(id),
    produto text NOT NULL,
    linha text NOT NULL CHECK (linha IN ('notebooks', 'celulares', 'acessorios')),
    valor numeric(10,2) NOT NULL,
    status text NOT NULL,
    data date NOT NULL
);

CREATE TABLE IF NOT EXISTS reembolsos (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    pedido_id text NOT NULL REFERENCES pedidos(id),
    cliente_id text NOT NULL REFERENCES clientes(id),
    valor numeric(10,2) NOT NULL,
    criado_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversas (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id text NOT NULL,
    titulo text,
    status text NOT NULL DEFAULT 'aberta'
        CHECK (status IN ('aberta', 'aprovacao_pendente', 'escalada', 'resolvida')),
    criada_em timestamptz NOT NULL DEFAULT now(),
    atualizada_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mensagens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversa_id uuid NOT NULL REFERENCES conversas(id),
    papel text NOT NULL CHECK (papel IN ('cliente', 'assistente')),
    conteudo text NOT NULL,
    message_id text UNIQUE,
    criada_em timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS fila_de_jobs (
    id bigserial PRIMARY KEY,
    tipo text NOT NULL CHECK (tipo IN ('mensagem', 'retomada')),
    conversa_id uuid NOT NULL REFERENCES conversas(id),
    message_id text UNIQUE,
    payload jsonb NOT NULL DEFAULT '{}',
    status text NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'processando', 'concluido', 'erro')),
    criado_em timestamptz NOT NULL DEFAULT now(),
    iniciado_em timestamptz,
    concluido_em timestamptz,
    erro text
);

CREATE INDEX IF NOT EXISTS fila_de_jobs_pendentes ON fila_de_jobs (id) WHERE status = 'pendente';

CREATE TABLE IF NOT EXISTS aprovacoes_pendentes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversa_id uuid NOT NULL REFERENCES conversas(id),
    cliente_id text NOT NULL,
    pedido_id text NOT NULL,
    valor numeric(10,2) NOT NULL,
    probabilidade double precision NOT NULL,
    resumo text NOT NULL,
    status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'aprovada', 'rejeitada')),
    motivo text,
    criada_em timestamptz NOT NULL DEFAULT now(),
    decidida_em timestamptz
);

CREATE TABLE IF NOT EXISTS tickets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversa_id uuid NOT NULL REFERENCES conversas(id),
    cliente_id text NOT NULL,
    resumo text NOT NULL,
    categoria text NOT NULL,
    prioridade text NOT NULL,
    criado_em timestamptz NOT NULL DEFAULT now()
);
