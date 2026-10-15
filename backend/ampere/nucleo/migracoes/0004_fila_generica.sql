-- A fila deixa de ser só do chat: um job pode não ter Conversa (a amostra ao vivo dos evals)
-- e publica num canal próprio. Canal nulo quer dizer "o canal da Conversa do job", então os
-- jobs gravados pela api antiga, enquanto o deploy troca as versões, continuam válidos.
ALTER TABLE fila_de_jobs ADD COLUMN IF NOT EXISTS canal text;
ALTER TABLE fila_de_jobs ALTER COLUMN conversa_id DROP NOT NULL;

ALTER TABLE fila_de_jobs DROP CONSTRAINT IF EXISTS fila_de_jobs_tipo_check;
ALTER TABLE fila_de_jobs ADD CONSTRAINT fila_de_jobs_tipo_check
    CHECK (tipo IN ('mensagem', 'retomada', 'eval'));
-- Só o job de eval vive sem Conversa, e todo job sabe onde publicar.
ALTER TABLE fila_de_jobs ADD CONSTRAINT fila_de_jobs_eval_sem_conversa
    CHECK (tipo = 'eval' OR conversa_id IS NOT NULL);
ALTER TABLE fila_de_jobs ADD CONSTRAINT fila_de_jobs_tem_canal
    CHECK (canal IS NOT NULL OR conversa_id IS NOT NULL);

-- A reserva olha os jobs anteriores da mesma Conversa (uma Conversa por vez).
CREATE INDEX IF NOT EXISTS fila_de_jobs_por_conversa ON fila_de_jobs (conversa_id, id)
    WHERE status IN ('pendente', 'processando');
