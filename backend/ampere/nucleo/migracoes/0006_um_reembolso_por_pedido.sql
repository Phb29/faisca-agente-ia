-- Um Reembolso por Pedido, garantido pelo banco.
--
-- A Ação emitir_reembolso confere se o Pedido já foi reembolsado e só depois grava. Com dois
-- workers, duas Conversas do mesmo Cliente podem conferir ao mesmo tempo, as duas veem
-- "ainda não reembolsado" e as duas gravam: o dinheiro sai duas vezes. A fila trava a
-- Conversa, não o Pedido. Com este índice, o segundo INSERT não entra (ON CONFLICT DO NOTHING
-- em loja/pedidos.py) e a Ação responde que o Pedido já foi reembolsado.
CREATE UNIQUE INDEX IF NOT EXISTS um_reembolso_por_pedido ON reembolsos (pedido_id);
