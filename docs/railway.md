# Deploy no Railway

O projeto roda em produção com cinco serviços num único projeto do Railway: `postgres`, `qdrant`, `api`, `worker` e `frontend`. Os três últimos vêm deste repositório, cada um com o root directory apontando para a sua subpasta, e o Railway constrói a imagem pelo `Dockerfile` que encontra lá. Tudo abaixo pode ser feito pelo painel (Settings de cada serviço) ou pelo CLI; os comandos do CLI estão indicados quando ajudam.

## 1. Projeto e repositório

Crie o projeto e conecte o repositório do GitHub uma vez. Pelo CLI, dentro do clone: `railway login`, `railway init --name suporte-ampere` e depois `railway link` se precisar religar. Cada serviço de código aponta para o mesmo repositório e branch, mudando só o root directory.

## 2. postgres (com pgvector)

O Store do LangGraph usa a extensão `vector` para a Memória Semântica, então o Postgres precisa de pgvector. O caminho mais simples é o template oficial de Postgres do Railway, cuja imagem já traz o pgvector: `railway deploy --template postgres`. Se preferir a mesma imagem do compose, crie um serviço a partir da imagem `pgvector/pgvector:pg16` com um volume montado em `/var/lib/postgresql/data` e as variáveis `POSTGRES_USER=ampere`, `POSTGRES_PASSWORD=<senha>` e `POSTGRES_DB=ampere`. Nos dois casos, o que a api e o worker precisam é a URL interna, que o template expõe como `${{Postgres.DATABASE_URL}}` (na imagem crua, monte à mão: `postgresql://ampere:<senha>@${{postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/ampere`).

## 3. qdrant

Serviço a partir da imagem `qdrant/qdrant` (o compose usa `v1.19.1`; fixe a mesma tag), com um volume montado em `/qdrant/storage`. Não precisa de domínio público: a api e o worker falam com ele pela rede privada em `http://${{qdrant.RAILWAY_PRIVATE_DOMAIN}}:6333`. Pelo CLI: `railway add --service qdrant --image qdrant/qdrant:v1.19.1` e depois `railway volume add --service qdrant --mount-path /qdrant/storage`.

## 4. api

Serviço a partir do repositório com root directory `backend`. O Railway detecta o `backend/Dockerfile`, que instala as dependências com `uv` e baixa os pesos do MiniLM, do BM25 e do ColBERT no build, para o container subir rápido. Configure:

- Root directory: `backend`
- Pre-deploy command: `ampere migrate` (aplica as migrações da fila e do login, inclusive a 0005 de sessões e tentativas, e prepara as tabelas do checkpointer e do Store antes de cada deploy)
- Start command: `ampere api --host :: --port $PORT` (o Railway injeta `PORT`; `--host ::` é obrigatório porque a rede interna do Railway é IPv6, e `0.0.0.0` não escuta nela)
- Healthcheck path: `/health` (responde 200 só quando Postgres e Qdrant respondem)
- Sem domínio público (ADR 0010): a api só é alcançada pela rede interna, em `api.railway.internal`, pelo frontend e pelo worker; não gere domínio em Settings → Networking

Pelo CLI, com o serviço criado e linkado:

```bash
railway environment edit --service-config api source.rootDirectory "/backend"
railway environment edit --service-config api deploy.preDeployCommand "ampere migrate"
railway environment edit --service-config api deploy.startCommand "ampere api --host :: --port \$PORT"
railway environment edit --service-config api deploy.healthcheckPath "/health"
```

## 5. worker

Mesmo repositório, mesmo root directory `backend`, mesma imagem resultante; só o start command muda: `ampere worker`. Sem domínio, sem healthcheck HTTP (o worker não abre porta) e sem pre-deploy (a api já migrou). O worker roda com duas réplicas (`numReplicas` 2, no painel em Settings → Deploy ou pela API do Railway): enquanto uma amostra ao vivo da Tela de Avaliação ocupa uma réplica por até um minuto, a outra atende o chat. A fila usa `SELECT FOR UPDATE SKIP LOCKED`, então réplicas não disputam o mesmo job, e a reserva pula o job que tem outro mais antigo da mesma Conversa em andamento, então duas mensagens da mesma Conversa nunca rodam juntas (ADR 0009). Cada réplica mantém uma só cópia do modelo de embedding MiniLM na memória, compartilhada pelo retriever, pela Memória Semântica e pela amostra do agente, então confira o uso de memória no painel depois da primeira amostra.

## 6. frontend

Root directory `frontend`. O navegador fala só com o frontend, que faz o papel de BFF e repassa cada chamada para a api (ADR 0010); por isso o frontend precisa de `API_INTERNA=http://api.railway.internal:8000`, apontando para a rede interna da api. Diferente do antigo `NEXT_PUBLIC_API_URL`, essa variável não entra no build: o `frontend/Dockerfile` não declara mais `ARG`, o BFF a lê em execução, então basta definir a variável no serviço. Gere um domínio público para o frontend; ele é a única porta de entrada do sistema. O container escuta na `3000`, que é a `PORT` padrão da imagem.

## Ordem do deploy e execuções dos evals

Quando uma mudança traz migração nova, o deploy segue a ordem api, worker e frontend, esperando cada um terminar: a api aplica as migrações no pre-deploy (a 0005, de sessões e tentativas, entre elas), e um worker novo que subisse antes delas falharia ao reservar jobs. Depois do deploy do frontend, confira pelo domínio dele que a rota de login responde e que qualquer página sem sessão cai em `/entrar` (ADR 0010); como a api não tem mais domínio público, é por aí que se confirma o deploy, não por um `curl` direto nela. As execuções completas que a Tela de Avaliação mostra são rodadas de dentro do worker, que enxerga o banco e tem as chaves: `railway ssh --service worker -- ampere-evals rag`, depois `agente` e `calibracao`. O RAG completo gasta a cota da Groq do trabalhador do chat; rode com folga antes da aula.

## Variáveis por serviço

| Variável | api | worker | frontend | Observação |
|---|---|---|---|---|
| `DATABASE_URL` | sim | sim | | `${{Postgres.DATABASE_URL}}` |
| `QDRANT_URL` | sim | sim | | `http://${{qdrant.RAILWAY_PRIVATE_DOMAIN}}:6333` |
| `OPENAI_API_KEY` | | sim | | gerador; a api não chama modelo |
| `GROQ_API_KEY` | | sim | | trabalhador |
| `TYPESAFE_API_KEY` | | sim | | Jev |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | | sim | | sem elas o tracing é no-op |
| `LOGIN_EMAIL` | sim | | | a conta que entra; `dono@exemplo.com.br` |
| `LOGIN_SENHA_HASH` | sim | | | só o hash, gerado com `uv run --project backend ampere hash-senha`; a senha não fica no Railway |
| `SESSAO_HORAS` | sim | | | validade da Sessão; `12` |
| `ORIGENS_PERMITIDAS` | sim | | | CORS, em JSON: `["https://<domínio do frontend>"]` |
| `EMBEDDER`, `CHUNKER`, `RERANKER`, `SELF_QUERYING` | sim | sim | | precisam ser iguais nos dois e iguais aos usados no `ingest` |
| `LIMIAR_*`, `VALOR_LIMITE_REEMBOLSO`, `LIMITE_MENSAGENS_RESUMO` | | sim | | opcionais, ver `.env.example` |
| `PROVEDOR_*`, `MODELO_*` | | sim | | opcionais; provedor e modelo de cada papel, ver `.env.example` |
| `API_INTERNA` | | | sim | a api pela rede interna: `http://api.railway.internal:8000` |

Use variáveis compartilhadas do ambiente para `DATABASE_URL`, `QDRANT_URL`, `EMBEDDER` e `CHUNKER`, referenciadas na api e no worker, para não divergirem. Pelo CLI: `railway variable set OPENAI_API_KEY=... --service worker`.

## Seed e ingest, uma vez

`migrate` roda sozinho a cada deploy da api, mas `seed` (Clientes, Pedidos e o Reembolso recente) e `ingest` (Base de Conhecimento no Qdrant) são executados à mão, uma vez, depois do primeiro deploy. Dois jeitos:

1. Shell dentro do container da api, que já tem a imagem, a rede privada e as variáveis: `railway ssh --service api` e então `ampere seed` e `ampere ingest` (ou `ampere ingest --todas` para as seis coleções do eval de RAG).
2. Da sua máquina, com as variáveis do serviço injetadas: `railway run --service api -- uv run ampere seed` e `railway run --service api -- uv run ampere ingest`. Isso exige que `DATABASE_URL` e `QDRANT_URL` sejam alcançáveis de fora (domínio público ou TCP proxy do Postgres e do Qdrant), então o primeiro jeito costuma ser mais simples.

Se trocar `EMBEDDER` ou `CHUNKER` depois, rode `ingest` de novo: a coleção do Qdrant é derivada desses dois nomes.

## Conferindo

`railway status --json` mostra o contexto; `railway logs --service worker --lines 200` mostra o worker pegando jobs. Como a api não tem domínio público, o `/health` só se confere de dentro da rede do Railway: `railway ssh --service api -- curl -s http://localhost:8000/health` deve devolver `{"status":"ok","postgres":true,"qdrant":true}`. Abra o domínio do frontend, entre com o login configurado, escolha um Cliente e mande uma mensagem; a resposta chega por SSE pelo mesmo caminho descrito no README raiz.
