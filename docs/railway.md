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
- Pre-deploy command: `ampere migrate` (aplica as migrações da fila e prepara as tabelas do checkpointer e do Store antes de cada deploy)
- Start command: `ampere api --port $PORT` (o Railway injeta `PORT`; o comando aceita a porta como opção)
- Healthcheck path: `/health` (responde 200 só quando Postgres e Qdrant respondem)
- Gere um domínio público em Settings → Networking; ele vira o `NEXT_PUBLIC_API_URL` do frontend

Pelo CLI, com o serviço criado e linkado:

```bash
railway environment edit --service-config api source.rootDirectory "/backend"
railway environment edit --service-config api deploy.preDeployCommand "ampere migrate"
railway environment edit --service-config api deploy.startCommand "ampere api --port \$PORT"
railway environment edit --service-config api deploy.healthcheckPath "/health"
railway domain --service api
```

## 5. worker

Mesmo repositório, mesmo root directory `backend`, mesma imagem resultante; só o start command muda: `ampere worker`. Sem domínio, sem healthcheck HTTP (o worker não abre porta) e sem pre-deploy (a api já migrou). Se quiser dois workers, suba `numReplicas` para 2: a fila usa `SELECT FOR UPDATE SKIP LOCKED`, então réplicas não disputam o mesmo job.

## 6. frontend

Root directory `frontend`. O `frontend/Dockerfile` gera a imagem standalone do Next e precisa de `NEXT_PUBLIC_API_URL` **no build**, porque o Next embute o valor no bundle. O Railway passa as variáveis do serviço como build args para o Dockerfile (o `ARG NEXT_PUBLIC_API_URL` já está declarado lá), então basta definir a variável no serviço com o domínio público da api, por exemplo `https://api-production-xxxx.up.railway.app`, e gerar um domínio público para o frontend. O container escuta na `3000`, que é a `PORT` padrão da imagem.

## Variáveis por serviço

| Variável | api | worker | frontend | Observação |
|---|---|---|---|---|
| `DATABASE_URL` | sim | sim | | `${{Postgres.DATABASE_URL}}` |
| `QDRANT_URL` | sim | sim | | `http://${{qdrant.RAILWAY_PRIVATE_DOMAIN}}:6333` |
| `OPENAI_API_KEY` | | sim | | gerador; a api não chama modelo |
| `GROQ_API_KEY` | | sim | | trabalhador |
| `TYPESAFE_API_KEY` | | sim | | Jev |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | | sim | | sem elas o tracing é no-op |
| `ATENDENTE_TOKEN` | sim | | | protege a Tela do Atendente; troque o padrão |
| `EMBEDDER`, `CHUNKER`, `RERANKER`, `SELF_QUERYING` | sim | sim | | precisam ser iguais nos dois e iguais aos usados no `ingest` |
| `LIMIAR_*`, `VALOR_LIMITE_REEMBOLSO`, `LIMITE_MENSAGENS_RESUMO` | | sim | | opcionais, ver `.env.example` |
| `NEXT_PUBLIC_API_URL` | | | sim | domínio público da api, usado no build |

Use variáveis compartilhadas do ambiente para `DATABASE_URL`, `QDRANT_URL`, `EMBEDDER` e `CHUNKER`, referenciadas na api e no worker, para não divergirem. Pelo CLI: `railway variable set OPENAI_API_KEY=... --service worker`.

## Seed e ingest, uma vez

`migrate` roda sozinho a cada deploy da api, mas `seed` (Clientes, Pedidos e o Reembolso recente) e `ingest` (Base de Conhecimento no Qdrant) são executados à mão, uma vez, depois do primeiro deploy. Dois jeitos:

1. Shell dentro do container da api, que já tem a imagem, a rede privada e as variáveis: `railway ssh --service api` e então `ampere seed` e `ampere ingest` (ou `ampere ingest --todas` para as seis coleções do eval de RAG).
2. Da sua máquina, com as variáveis do serviço injetadas: `railway run --service api -- uv run ampere seed` e `railway run --service api -- uv run ampere ingest`. Isso exige que `DATABASE_URL` e `QDRANT_URL` sejam alcançáveis de fora (domínio público ou TCP proxy do Postgres e do Qdrant), então o primeiro jeito costuma ser mais simples.

Se trocar `EMBEDDER` ou `CHUNKER` depois, rode `ingest` de novo: a coleção do Qdrant é derivada desses dois nomes.

## Conferindo

`railway status --json` mostra o contexto; `railway logs --service worker --lines 200` mostra o worker pegando jobs; `curl https://<domínio da api>/health` deve devolver `{"status":"ok","postgres":true,"qdrant":true}`. Abra o domínio do frontend, escolha um Cliente e mande uma mensagem; a resposta chega por SSE pelo mesmo caminho descrito no README raiz.
