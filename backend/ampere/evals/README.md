# Evals

Três evals, três CSVs em `dados/`, nenhum roda no pytest porque todos gastam modelo de verdade. O eval do RAG (`golden_rag.csv`: pergunta, documento esperado, resposta de referência) mede Recall@5 e MRR no nível do documento para cada coleção do Qdrant, com e sem ColBERT e com e sem self-querying, e pede ao juiz duas perguntas binárias com crítica sobre a geração: a resposta é fiel aos trechos e é relevante à pergunta. O eval do agente (`golden_agente.csv`: mensagem, estado inicial, intenção, Ação e desfecho esperados) roda um turno do grafo real por cenário, compara intenção, Ação e desfecho por código e pergunta ao juiz se a resposta resolve sem prometer nada fora da política. A calibração (`rotulos_humanos.csv`: sessenta respostas rotuladas à mão como Aprovada ou Reprovada) divide os rótulos em treino, dev e teste; o treino vira few-shot do prompt do juiz, o dev mede TPR e TNR e mostra cada desacordo entre juiz e humano, e o teste recebe a correção. O juiz é outro modelo que o gerador (ADR 0002) porque um modelo tende a aprovar a própria escrita, e calibrar contra humano é o que transforma "o juiz aprovou 80%" num número em que se pode confiar: Rogan-Gladen usa o TPR e o TNR medidos no dev para corrigir a taxa crua de aprovação pelo viés do juiz, e o bootstrap dá o intervalo de confiança dessa correção. Os prompts do juiz ficam em `prompts/` com nome e versão; com chaves do Langfuse no `.env`, cada eval publica o golden como dataset e cada variante ou execução como run com os scores por item.

Como rodar, a partir de `backend/`, com Qdrant ingerido (`uv run ampere ingest --todas`) e as chaves no `.env`:

```bash
uv run ampere-evals rag                  # todas as variantes; geração + juiz só na variante do .env
uv run ampere-evals rag --so-retrieval   # só Recall@5 e MRR, sem gastar gerador nem juiz
uv run ampere-evals rag --amostra 10     # as 10 primeiras perguntas
uv run ampere-evals agente               # um turno por cenário, tabela por dimensão e veredito
uv run ampere-evals agente --amostra 5
uv run ampere-evals calibracao           # TPR, TNR, matriz, desacordos e Rogan-Gladen com IC
```
