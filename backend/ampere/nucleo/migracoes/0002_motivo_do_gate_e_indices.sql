-- O cartão da Aprovação Pendente mostra ao Atendente por que o Gate pediu aprovação
-- (valor acima do limite, Reembolso recente ou a probabilidade do Jev).
ALTER TABLE aprovacoes_pendentes ADD COLUMN IF NOT EXISTS motivo_do_gate text;

-- Leituras mais comuns: as Conversas de um Cliente e as mensagens de uma Conversa.
CREATE INDEX IF NOT EXISTS conversas_por_cliente ON conversas (cliente_id, criada_em DESC);
CREATE INDEX IF NOT EXISTS mensagens_por_conversa ON mensagens (conversa_id, criada_em);
