# Suporte Ampère

Chatbot de suporte ao Cliente da **Ampère Eletrônicos**, um e-commerce fictício, construído para um workshop ao vivo sobre engenharia de IA em produção. O Cliente conversa pelo chat; o chatbot responde dúvidas de política a partir da Base de Conhecimento (RAG híbrido no Qdrant), consulta Pedidos, emite Reembolsos (pedindo aprovação de um Atendente quando o Gate de Aprovação julga o caso crítico) e abre Tickets quando não consegue resolver. Por trás: um grafo do LangGraph com oito nós, o Jev (TypeSafe) como motor de todas as decisões rápidas, três papéis de modelo, Postgres para memória e fila, Langfuse para traces e dois evals com juiz calibrado contra rótulos humanos. Tudo pequeno o bastante para caber numa aula e completo o bastante para ser produção. Vocabulário em [CONTEXT.md](CONTEXT.md); decisões em [docs/adr](docs/adr).

## O grafo

```mermaid
flowchart TD
    START([mensagem do Cliente]) --> CM[carregar_memoria]
    CM --> GE[guardrail_entrada<br/>Jev: manipulação, fora de escopo, dado sensível]
    GE -- bloqueio: resposta fixa --> SM
    GE --> RO[roteador<br/>Jev: duvida, transacao, quer_humano]
    RO -- duvida --> RC[recuperar_contexto<br/>busca híbrida no Qdrant]
    RC --> GR[gerar_resposta<br/>gerador, sem tools]
    RO -- transacao --> AG[agente<br/>gerador + 4 Ações]
    RO -- quer_humano --> AG
    AG -- tool calls --> AG
    AG -. emitir_reembolso crítico: interrupt<br/>Aprovação Pendente, retomada por Command(resume) .-> AG
    GR --> GS[guardrail_saida<br/>Jev: fora do contexto, promessa indevida, vazamento]
    AG --> GS
    GS -- aprovada --> SM[salvar_memoria<br/>trabalhador: fatos, episódio, resumo]
    GS -- reprovada, 1ª vez: volta com a crítica --> GR
    GS -- reprovada, 1ª vez: volta com a crítica --> AG
    GS -- reprovada, 2ª vez: abre Ticket e escala --> SM
    SM --> FIM([resposta])
```

A volta ao gerador acontece uma única vez: no caminho `duvida` ela vai para `gerar_resposta`, nos outros dois para `agente`. Na segunda reprovação o grafo abre um Ticket e devolve uma resposta fixa. Cada nó tem o system prompt num arquivo próprio em [backend/ampere/grafo/prompts](backend/ampere/grafo/prompts).

## A infraestrutura

```mermaid
flowchart LR
    FE[frontend<br/>Next.js] -- REST + SSE --> API[api<br/>FastAPI]
    API -- INSERT na fila, 202 --> PG[(Postgres<br/>fila, mensagens, Aprovações, Tickets,<br/>checkpointer e Store do LangGraph)]
    PG -- SELECT FOR UPDATE SKIP LOCKED --> WK[worker<br/>executa o grafo]
    WK -- NOTIFY por Conversa --> PG
    PG -- LISTEN --> API
    WK --> QD[(Qdrant<br/>busca híbrida)]
    WK --> JEV[Jev / TypeSafe<br/>Guardrails, Roteador, Gate]
    WK --> LLM[OpenAI e Groq<br/>gerador e trabalhador]
    WK --> LF[Langfuse Cloud<br/>traces]
    API --> QD
```

A api e o worker rodam a mesma imagem Docker com comandos diferentes. Não há Redis nem broker: a fila, a idempotência do `message_id` e o stream de tokens (LISTEN/NOTIFY → SSE) vivem no Postgres ([ADR 0004](docs/adr/0004-fila-e-stream-no-postgres.md)).

## Como rodar

```bash
cp .env.example .env                      # sem chaves? deixe MODELOS_FALSOS=true
docker compose up -d postgres qdrant      # Postgres na 5439, Qdrant na 6333

cd backend && uv sync
uv run ampere migrate                     # tabelas da fila, das Conversas e do LangGraph
uv run ampere seed                        # três Clientes, Pedidos e um Reembolso recente
uv run ampere ingest                      # Base de Conhecimento no Qdrant (ou --todas: as seis coleções)
uv run ampere api                         # http://localhost:8000
uv run ampere worker                      # em outro terminal

cd ../frontend && npm install && npm run dev   # http://localhost:3000 (chat) e /atendente
```

Ou tudo de uma vez, incluindo api, worker e frontend em containers: `docker compose up --build`. Nesse caso rode `migrate`, `seed` e `ingest` de dentro do container: `docker compose run --rm api ampere migrate` (e o mesmo para `seed` e `ingest`). Todas as variáveis estão comentadas em [.env.example](.env.example).

**Testes:** `cd backend && uv run pytest`. Unitários e o teste do grafo inteiro rodam sem nada; os de integração (`-m integracao`) precisam de `DATABASE_URL` e `QDRANT_URL` apontando para o compose. Nenhum teste gasta token nem precisa de chave, e o [CI](.github/workflows/ci.yml) roda tudo assim. Frontend: `npm run lint && npx tsc --noEmit && npm run build`.

**Evals** (não são testes, ficam fora do pytest e gastam token): `uv run ampere-evals rag` (Recall@5 e MRR por coleção, com e sem ColBERT e self-querying, mais fidelidade e relevância pelo juiz), `uv run ampere-evals agente` (intenção, Ação e desfecho por código, veredito e crítica do juiz) e `uv run ampere-evals calibracao` (TPR, TNR, matriz de confusão, desacordos e Rogan-Gladen com bootstrap contra os rótulos humanos). Dados em [backend/ampere/evals/dados](backend/ampere/evals/dados).

## Custo por papel

Modelo caro não é para tudo ([ADR 0002](docs/adr/0002-tres-niveis-de-modelo.md)). Valores em USD por milhão de tokens, de `CUSTO_POR_PAPEL` em [backend/ampere/nucleo/modelos.py](backend/ampere/nucleo/modelos.py).

| Papel | Modelo | Entrada | Saída | Faz o quê |
|---|---|---|---|---|
| gerador | gpt-5.6-terra (OpenAI) | 2,50 | 10,00 | escreve para o Cliente e escolhe as Ações |
| juiz | gpt-5.6-sol (OpenAI) | 15,00 | 60,00 | só nos evals; avalia respostas com crítica |
| trabalhador | openai/gpt-oss-120b (Groq) | 0,15 | 0,60 | extrai memórias, resume Conversas e Tickets, self-querying |

O Jev não entra na tabela: não gera texto, responde perguntas tipadas com probabilidade calibrada em milissegundos ([ADR 0001](docs/adr/0001-jev-decide-llm-escreve.md)).

## Índice na ordem da aula

A ordem em que uma mensagem atravessa o sistema. Cada pasta tem um README curto: o que é, por que foi feito assim e um parágrafo de teoria.

1. [api](backend/ampere/api) e [fila](backend/ampere/fila): REST, 202 idempotente, worker com SKIP LOCKED, NOTIFY e os cinco eventos do SSE
2. [grafo](backend/ampere/grafo): os oito nós, o estado e os prompts
3. [guardrails](backend/ampere/guardrails): entrada, saída e mascaramento
4. [roteador](backend/ampere/roteador): a intenção que escolhe o caminho
5. [rag](backend/ampere/rag): chunkers, embedders, busca híbrida, ColBERT e self-querying
6. [acoes](backend/ampere/acoes): as quatro Ações e o human-in-the-loop do Reembolso
7. [memoria](backend/ampere/memoria): Semântica, Episódica e Procedural
8. [observabilidade](backend/ampere/observabilidade): Langfuse, sessões e spans do Jev
9. [evals](backend/ampere/evals): RAG, agente e calibração do juiz
10. [nucleo](backend/ampere/nucleo): config, fábrica de modelos, Jev e falsos

Também: [frontend](frontend), [tests](backend/tests), [CONTEXT.md](CONTEXT.md) (glossário) e as ADRs:

- [0001 Jev decide, LLM escreve](docs/adr/0001-jev-decide-llm-escreve.md)
- [0002 Três papéis de modelo: gerador, juiz e trabalhador](docs/adr/0002-tres-niveis-de-modelo.md)
- [0003 Qdrant como único índice de busca, uma coleção por variante](docs/adr/0003-qdrant-como-unico-indice-de-busca.md)
- [0004 Fila, idempotência e stream de tokens no Postgres](docs/adr/0004-fila-e-stream-no-postgres.md)
- [0005 Backend organizado por conceito de domínio, não por camada](docs/adr/0005-organizacao-por-conceito.md)
- [0006 Identificadores de domínio em português, técnicos em inglês](docs/adr/0006-dominio-em-portugues.md)

Deploy em produção, com cinco serviços no Railway: [docs/railway.md](docs/railway.md). Licença [MIT](LICENSE).
