-- Cada rodada de um eval: a completa, gravada pelo CLI, e a amostra ao vivo, gravada caso a
-- caso pelo worker (ver docs/adr/0009). `casos` cresce um caso por vez enquanto a amostra anda.
CREATE TABLE IF NOT EXISTS execucoes_de_eval (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    eval text NOT NULL CHECK (eval IN ('rag', 'agente', 'juiz')),
    modo text NOT NULL CHECK (modo IN ('completa', 'amostra')),
    status text NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'rodando', 'concluida', 'erro')),
    contexto jsonb NOT NULL DEFAULT '{}',
    resumo jsonb,
    casos jsonb NOT NULL DEFAULT '[]',
    erro text,
    criada_em timestamptz NOT NULL DEFAULT now(),
    iniciada_em timestamptz,
    concluida_em timestamptz
);

CREATE INDEX IF NOT EXISTS execucoes_de_eval_recentes ON execucoes_de_eval (eval, criada_em DESC);

-- No máximo uma amostra em andamento, de qualquer eval, garantido pelo banco: dois cliques
-- ao mesmo tempo não criam duas.
CREATE UNIQUE INDEX IF NOT EXISTS uma_amostra_por_vez ON execucoes_de_eval (modo)
    WHERE modo = 'amostra' AND status IN ('pendente', 'rodando');
