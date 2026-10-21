# Suporte Ampère

Chatbot de suporte ao Cliente da **Ampère Eletrônicos**, um e-commerce fictício, construído para um workshop ao vivo sobre engenharia de IA em produção. O Cliente conversa pelo chat; o chatbot responde dúvidas de política a partir da Base de Conhecimento (RAG híbrido no Qdrant), consulta Pedidos, emite Reembolsos (pedindo aprovação de um Atendente quando o Gate de Aprovação julga o caso crítico) e abre Tickets quando não consegue resolver. Por trás: um grafo do LangGraph com nove nós, o Jev (TypeSafe) como motor de todas as decisões rápidas, regras dessas decisões escritas em YAML legível, três papéis de modelo, Postgres para memória e fila, Langfuse para traces e dois evals com juiz calibrado contra rótulos humanos. Tudo pequeno o bastante para caber numa aula e completo o bastante para ser produção. Vocabulário em [CONTEXT.md](CONTEXT.md); decisões em [docs/adr](docs/adr).

## O grafo

```mermaid
flowchart TD
    START([mensagem do Cliente]) --> CM[carregar_memoria]
    CM --> GE[guardrail_entrada<br/>Jev: manipulação, fora de escopo, dado sensível]
    GE -- bloqueio: resposta fixa --> SM
    GE --> RO[roteador<br/>Jev: duvida, transacao, quer_humano]
    RO -- duvida --> RC[recuperar_contexto<br/>busca híbrida no Qdrant]
    RC --> GR[gerar_resposta<br/>gerador, sem Ações]
    RO -- transacao --> AG[agente<br/>gerador + 4 Ações]
    RO -- quer_humano --> ES[escalar<br/>abre Ticket, resposta fixa]
    AG -- pede Ações --> AG
    AG -. Reembolso crítico: Gate decide e grava,<br/>interrupt vira Aprovação Pendente,<br/>Command resume retoma .-> AG
    GR --> GS[guardrail_saida<br/>Jev: fora do contexto, promessa indevida, vazamento]
    AG --> GS
    GS -- aprovada --> SM[salvar_memoria<br/>trabalhador: fatos, episódio, resumo]
    GS -- reprovada, 1ª vez: volta com a crítica --> GR
    GS -- reprovada, 1ª vez: volta com a crítica --> AG
    GS -- reprovada, 2ª vez --> ES
    ES --> SM
    SM --> FIM([resposta])
```

A volta ao gerador acontece uma única vez: no caminho `duvida` ela vai para `gerar_resposta`, no caminho `transacao` para `agente`. Na segunda reprovação o grafo escala: abre um Ticket e devolve uma resposta fixa. Respostas fixas (bloqueio e escalada) não passam pelo Guardrail de saída, porque não foram escritas por um modelo. Tudo o que um modelo lê está em [backend/ampere/prompts](backend/ampere/prompts), e tudo o que o Jev decide está em [backend/ampere/regras](backend/ampere/regras), em YAML que qualquer pessoa lê: a pergunta, quando é sim, quando é não e o que acontece quando dispara.

## A infraestrutura

```mermaid
flowchart LR
    FE[frontend<br/>Next.js] -- REST + SSE --> API[api<br/>FastAPI]
    API -- mascara, INSERT na fila,<br/>NOTIFY fila_de_jobs, 202 --> PG[(Postgres<br/>fila, mensagens, Aprovações, Tickets,<br/>checkpointer e Store do LangGraph)]
    PG -- LISTEN + SKIP LOCKED --> WK[worker<br/>executa o grafo]
    WK -- NOTIFY por Conversa --> PG
    PG -- LISTEN --> API
    WK --> QD[(Qdrant<br/>busca híbrida)]
    WK --> JEV[Jev / TypeSafe<br/>Guardrails, Roteador, Gate]
    WK --> LLM[OpenAI e Groq<br/>gerador e trabalhador]
    WK --> LF[Langfuse Cloud<br/>traces]
    API --> QD
```

A api e o worker rodam a mesma imagem Docker com comandos diferentes e usam um pool de conexões. Não há Redis nem broker: a fila, a idempotência do `message_id`, o aviso que acorda o worker e o stream de eventos (LISTEN/NOTIFY → SSE) vivem no Postgres ([ADR 0004](docs/adr/0004-fila-e-stream-no-postgres.md)). O SSE entrega seis eventos: `token`, `tool_call`, `etapa` (um por nó do grafo, para o painel de bastidores do chat), `approval_required`, `message_done` e `error`. Cartão, CPF, CVV e senha são mascarados na api, antes de qualquer gravação.

## Como subir localmente

**Pré-requisitos:** [Docker](https://docs.docker.com/get-docker/) com Compose v2 (Docker Desktop no Mac e no Windows), [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.8 ou mais novo (`uv self update` atualiza; ele baixa sozinho o Python 3.12 que o backend exige; não precisa instalar Python), [Node.js](https://nodejs.org/) 22 ou mais novo, com o npm que vem junto, e Git. Reserve uns 2 GB de disco: imagens do Postgres e do Qdrant, dependências do backend e do frontend e os modelos de embedding que o primeiro `ingest` baixa (perto de 400 MB).

**Chaves:** sem nenhuma, o sistema roda inteiro no modo demonstração (`MODELOS_FALSOS=true`, mais abaixo). Com os modelos de verdade e os provedores padrão do [.env.example](.env.example), são três obrigatórias:

| Variável | Para quê | Obrigatória? | Onde pegar |
|---|---|---|---|
| `OPENAI_API_KEY` | gerador (o chat) e juiz (os evals) | sim | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `GROQ_API_KEY` | trabalhador: memória, resumos e self-querying | sim, enquanto `PROVEDOR_TRABALHADOR=groq` (o padrão); sem ela o worker não sobe | [console.groq.com/keys](https://console.groq.com/keys) |
| `TYPESAFE_API_KEY` | o Jev: Guardrails, Roteador e Gate de Aprovação | sim | [typesafe.ai](https://typesafe.ai) |
| `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY` | traces e custo por chamada | não: sem elas o tracing desliga e o resto funciona igual | [cloud.langfuse.com](https://cloud.langfuse.com), nas configurações do projeto |

Quem não tem conta na Groq pode pôr o trabalhador na OpenAI: `PROVEDOR_TRABALHADOR=openai` e um modelo da OpenAI em `MODELO_TRABALHADOR` (o mesmo `gpt-6-luna` do gerador serve).

**Passo a passo**, sempre a partir da raiz do repositório:

```bash
# 1. Variáveis: preencha as chaves no .env, ou ponha MODELOS_FALSOS=true
cp .env.example .env
cp frontend/.env.example frontend/.env.local

# 2. Login: crie a senha e copie o hash para LOGIN_SENHA_HASH no .env,
#    junto com o seu e-mail em LOGIN_EMAIL (a senha em si não fica em lugar nenhum)
uv run --project backend ampere hash-senha    # pede a senha duas vezes e imprime scrypt:...

# 3. Infra: Postgres na 5439 e Qdrant na 6333
docker compose up -d postgres qdrant

# 4. Banco e Base de Conhecimento
uv run --project backend ampere migrate       # tabelas da fila, das Conversas, do login e do LangGraph
uv run --project backend ampere seed          # três Clientes, Pedidos e um Reembolso recente
uv run --project backend ampere ingest        # Base de Conhecimento no Qdrant (ou --todas: as seis coleções)

# 5. api e worker, cada um no seu terminal
uv run --project backend ampere api           # http://localhost:8000
uv run --project backend ampere worker

# 6. frontend, em outro terminal
cd frontend && npm install && npm run dev     # http://localhost:3000
```

Abra `http://localhost:3000`: sem sessão, a página leva para `/entrar`, onde vale o e-mail de `LOGIN_EMAIL` com a senha que você digitou no `hash-senha`. Depois do login, escolha um dos Clientes de exemplo (Ana, Bruno ou Carla) e converse; a Central do Atendente fica em `/atendente` e a Tela de Avaliação em `/avaliacao`. O primeiro `uv run` cria o ambiente do backend e instala tudo sozinho, então demora um pouco mais; o primeiro `ingest` baixa os modelos de embedding.

Por que da raiz com `--project backend`: os comandos `ampere` leem o `.env` da pasta onde rodam. Rodando de dentro de `backend/`, o `.env` da raiz fica de fora, a api sobe com o login desligado (ninguém entra) e o worker cai na hora por falta das chaves. Se aparecer `Login desligado` no log da api ou `api_key ... must be set` no worker, é isso.

**Portas:** frontend na 3000, api na 8000, Postgres na 5439 (e não na 5432, para não brigar com um Postgres instalado na máquina) e Qdrant na 6333, com o painel em `http://localhost:6333/dashboard`. O compose abre o Postgres, o Qdrant e a api só no `127.0.0.1`, fora da rede local. Se a 3000 estiver ocupada, `npm run dev -- -p 3010`. Se a 8000 estiver, `uv run --project backend ampere api --port 8010` e `API_INTERNA=http://localhost:8010` no `frontend/.env.local`. Se a 5439 estiver, `POSTGRES_PORT=5440` no `.env` e a mesma porta no `DATABASE_URL`.

**`BFF_SEGREDO`:** no local pode ficar vazio. Se preencher (gere com `openssl rand -base64 32`), ponha o mesmo valor no `.env` da raiz e no `frontend/.env.local`; se a api tiver um segredo e o frontend não tiver o mesmo, toda chamada volta 403 `Origem não autorizada`.

**Modo demonstração:** com `MODELOS_FALSOS=true` o sistema roda inteiro sem nenhuma chave: dublês do gerador, do trabalhador e do Jev reagem à mensagem por palavras-chave, então dá para demonstrar dúvida, consulta de Pedido, Reembolso com e sem Atendente, escalada e bloqueios mesmo se a OpenAI ou o Jev caírem no dia. Rode o `ingest` no mesmo modo, porque o embedder também vira falso. A coleção do Qdrant tem o mesmo nome nos dois modos, então ao voltar para os modelos de verdade rode o `ingest` de novo, senão a busca usa os vetores falsos.

**Tudo em containers:** `docker compose up --build` sobe também a api, o worker e o frontend, lendo o mesmo `.env` da raiz. Nesse caso rode `migrate`, `seed` e `ingest` de dentro do container: `docker compose run --rm api ampere migrate` (e o mesmo para `seed` e `ingest`). As imagens ocupam perto de 3 GB a mais (a do backend já traz os modelos de embedding). O frontend do container roda em modo de produção, com o cookie da sessão `Secure`: o Chrome aceita esse cookie em `http://localhost`, mas o Safari recusa e devolve você para `/entrar` depois do login. No Safari, use o frontend do `npm run dev`.

**Recomeçar do zero:** `docker compose down -v` apaga o Postgres e o Qdrant (Conversas, memória, Tickets, sessões e a Base de Conhecimento); depois repita `migrate`, `seed` e `ingest`. Para derrubar todas as sessões abertas, troque a senha (gere outro hash) ou o e-mail e reinicie a api. Errou a senha demais? O login aceita 5 falhas por IP e 20 por e-mail a cada 15 minutos; espere a janela passar ou limpe as tentativas com `docker compose exec postgres psql -U ampere -c "DELETE FROM tentativas_de_login"`.

Todas as variáveis estão comentadas em [.env.example](.env.example) e [frontend/.env.example](frontend/.env.example).

**Testes:** `cd backend && uv run pytest`, de dentro de `backend/` de propósito, para o `.env` da raiz e as suas chaves ficarem de fora. Unitários e o teste do grafo inteiro rodam sem nada; os de integração (`-m integracao`) pulam sozinhos sem `DATABASE_URL` no ambiente e, com o compose no ar, rodam com `DATABASE_URL=postgresql://ampere:ampere@localhost:5439/ampere QDRANT_URL=http://localhost:6333 MODELOS_FALSOS=true uv run pytest`. Nenhum teste gasta token nem precisa de chave, e o [CI](.github/workflows/ci.yml) roda tudo assim. A regra de acoplamento da [ADR 0005](docs/adr/0005-organizacao-por-conceito.md) também é um teste. Frontend: `npm run lint && npx tsc --noEmit && npm run build`.

**Evals** (não são testes, ficam fora do pytest e gastam token; rode da raiz, para o `.env` com as chaves valer): `uv run --project backend ampere-evals rag` (Recall@5 e MRR por coleção, com e sem ColBERT e self-querying, mais fidelidade e relevância pelo juiz), `uv run --project backend ampere-evals agente` (intenção, Ação e desfecho por código, veredito e crítica do juiz) e `uv run --project backend ampere-evals calibracao` (TPR, TNR, matriz de confusão, desacordos e Rogan-Gladen com bootstrap contra os rótulos humanos). Dados em [backend/ampere/evals/dados](backend/ampere/evals/dados).

## Segurança

O `.env` e o `frontend/.env.local` guardam as suas chaves e já estão no `.gitignore`: nunca faça commit deles, e se uma chave vazar, revogue no painel do provedor. Cada mensagem do chat e cada amostra da Tela de Avaliação gasta tokens das suas contas, e é o login que protege esse gasto: use uma senha forte, só sua.

O que está no repositório é feito para a sua máquina. Antes de pôr no ar: gere uma senha e um hash novos, ponha um `BFF_SEGREDO` aleatório e igual na api e no frontend, preencha `ORIGEM_PUBLICA` (frontend) e `ORIGENS_PERMITIDAS` (api) com o domínio do frontend, deixe a api, o Postgres e o Qdrant sem endereço público (só o frontend fica exposto) e troque a senha `ampere` do Postgres. O `docker-compose.yml` não serve para servidor como está: a senha do banco é fixa e o Qdrant não tem chave. O caminho de produção, com essas variáveis por serviço, está em [docs/railway.md](docs/railway.md).

## Custo por papel

Modelo caro não é para tudo ([ADR 0002](docs/adr/0002-tres-niveis-de-modelo.md)). O modelo de cada papel vem do `.env` (`MODELO_GERADOR`, `MODELO_JUIZ`, `MODELO_TRABALHADOR`); a tabela abaixo é a de produção. Valores em USD por milhão de tokens, consultados em 16/10/2026 na [página de preços da OpenAI](https://developers.openai.com/api/docs/pricing) e na [ficha do modelo na Groq](https://console.groq.com/docs/model/openai/gpt-oss-120b).

| Papel | Modelo | Entrada | Saída | Faz o quê |
|---|---|---|---|---|
| gerador | gpt-6-luna (OpenAI) | 0,10 | 0,50 | escreve para o Cliente e escolhe as Ações |
| juiz | gpt-6.1-sol (OpenAI) | 2,00 | 10,00 | só nos evals; avalia respostas com crítica |
| trabalhador | openai/gpt-oss-120b (Groq) | 0,15 | 0,60 | extrai memórias, resume Conversas e Tickets, self-querying |

O preço não mora no código: o custo medido de cada chamada sai do trace no Langfuse, que calcula pelos tokens. O gpt-6-luna e o gpt-6.1-sol já vêm com preço no Langfuse; o gpt-oss-120b da Groq foi cadastrado à mão (Settings > Models), com os tokens de raciocínio cobrados como saída. Ao trocar de modelo, confira se o Langfuse conhece o preço do novo: se não conhecer, o custo daquele papel aparece como zero.

O Jev não entra na tabela: não gera texto, responde perguntas tipadas com probabilidade calibrada em milissegundos ([ADR 0001](docs/adr/0001-jev-decide-llm-escreve.md)).

## Índice na ordem da aula

A ordem em que uma mensagem atravessa o sistema. Cada pasta tem um README curto: o que é, por que foi feito assim e um parágrafo de teoria.

1. [api](backend/ampere/api), [fila](backend/ampere/fila) e [conversas](backend/ampere/conversas): REST, mascaramento na borda, 202 idempotente, worker com SKIP LOCKED, NOTIFY e os eventos do SSE
2. [grafo](backend/ampere/grafo): os nove nós, o estado e o executor
3. [prompts](backend/ampere/prompts) e [regras](backend/ampere/regras): tudo o que os modelos e o Jev leem, em texto
4. [guardrails](backend/ampere/guardrails): entrada, saída e mascaramento
5. [roteador](backend/ampere/roteador): a intenção que escolhe o caminho
6. [rag](backend/ampere/rag): chunkers, embedders, busca híbrida, ColBERT e self-querying
7. [acoes](backend/ampere/acoes) e [loja](backend/ampere/loja): as quatro Ações, o Gate de Aprovação e o human-in-the-loop do Reembolso
8. [memoria](backend/ampere/memoria): Semântica, Episódica e Procedural
9. [observabilidade](backend/ampere/observabilidade): Langfuse, sessões e spans do Jev
10. [evals](backend/ampere/evals): RAG, agente, calibração do juiz e a Tela de Avaliação (`/avaliacao`), com a amostra ao vivo
11. [nucleo](backend/ampere/nucleo): config, fábrica de modelos, Jev, falsos, banco e migrações

Também: [frontend](frontend), [tests](backend/tests), [CONTEXT.md](CONTEXT.md) (glossário), a raiz de composição em [backend/ampere/composicao.py](backend/ampere/composicao.py) e as ADRs:

- [0001 Jev decide, LLM escreve](docs/adr/0001-jev-decide-llm-escreve.md)
- [0002 Três papéis de modelo: gerador, juiz e trabalhador](docs/adr/0002-tres-niveis-de-modelo.md)
- [0003 Qdrant como único índice de busca, uma coleção por variante](docs/adr/0003-qdrant-como-unico-indice-de-busca.md)
- [0004 Fila, idempotência e stream de tokens no Postgres](docs/adr/0004-fila-e-stream-no-postgres.md)
- [0005 Backend organizado por conceito de domínio, não por camada](docs/adr/0005-organizacao-por-conceito.md)
- [0006 Identificadores de domínio em português, técnicos em inglês](docs/adr/0006-dominio-em-portugues.md)
- [0007 Regras do Jev em YAML legível, fora do código](docs/adr/0007-regras-do-jev-em-yaml.md)
- [0008 Fornecedores atrás de interfaces do projeto, sem reorganizar em camadas](docs/adr/0008-fornecedores-atras-de-interfaces.md)
- [0009 Avaliação ao vivo pela mesma fila e pelo mesmo stream do chat](docs/adr/0009-avaliacao-ao-vivo-pela-fila.md)
- [0010 Login com sessão no Postgres e frontend como BFF](docs/adr/0010-login-com-sessao-e-frontend-como-bff.md)

Deploy em produção, com cinco serviços no Railway: [docs/railway.md](docs/railway.md). Licença [MIT](LICENSE).
