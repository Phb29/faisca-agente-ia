-- Login: as sessões abertas e as tentativas de entrar (ver ampere/acesso).
-- `sessoes.id` é o sha256 do token: quem lê o banco não consegue se passar por ninguém.
-- `credencial` é a marca do e-mail e do hash da senha da conta quando a sessão abriu: trocar
-- a senha ou o e-mail derruba as sessões abertas antes.
CREATE TABLE IF NOT EXISTS sessoes (
    id text PRIMARY KEY,
    email text NOT NULL,
    credencial text NOT NULL,
    criada_em timestamptz NOT NULL DEFAULT now(),
    expira_em timestamptz NOT NULL,
    ip text NOT NULL,
    user_agent text NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS sessoes_por_expiracao ON sessoes (expira_em);

-- O limite de tentativas mora aqui, e não na memória do processo, para valer igual com
-- várias réplicas da api.
CREATE TABLE IF NOT EXISTS tentativas_de_login (
    id bigserial PRIMARY KEY,
    email text NOT NULL,
    ip text NOT NULL,
    sucesso boolean NOT NULL,
    momento timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS tentativas_por_ip ON tentativas_de_login (ip, momento);
CREATE INDEX IF NOT EXISTS tentativas_por_email ON tentativas_de_login (email, momento);
-- Os sucessos dizem de quais IPs a conta já entrou: dali, o limite por e-mail não vale.
CREATE INDEX IF NOT EXISTS sucessos_por_email_e_ip ON tentativas_de_login (email, ip, momento)
    WHERE sucesso;
