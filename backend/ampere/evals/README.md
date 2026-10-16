# Evals

Três evals, três CSVs em `dados/`, nenhum roda no pytest porque todos gastam modelo de verdade. O eval do RAG (`golden_rag.csv`: pergunta, documento esperado, resposta de referência) mede Recall@5 e MRR no nível do documento para cada coleção do Qdrant, com e sem ColBERT e com e sem self-querying, e pede ao juiz duas perguntas binárias com crítica sobre a geração: a resposta é fiel aos trechos e é relevante à pergunta. O eval do agente (`golden_agente.csv`: mensagem, estado inicial, intenção, Ação e desfecho esperados) roda um turno do grafo real por cenário, compara intenção, Ação e desfecho por código e pergunta ao juiz se a resposta resolve sem prometer nada fora da política. A calibração (`rotulos_humanos.csv`: sessenta respostas rotuladas à mão como Aprovada ou Reprovada) divide os rótulos em treino, dev e teste; o treino vira few-shot do prompt do juiz, o dev mede TPR e TNR e mostra cada desacordo entre juiz e humano, e o teste recebe a correção. O juiz é outro modelo que o gerador (ADR 0002) porque um modelo tende a aprovar a própria escrita, e calibrar contra humano é o que transforma "o juiz aprovou 80%" num número em que se pode confiar: Rogan-Gladen usa o TPR e o TNR medidos no dev para corrigir a taxa crua de aprovação pelo viés do juiz, e o bootstrap dá o intervalo de confiança dessa correção. Os prompts do juiz ficam em `ampere/prompts/juiz_*.md`, com nome e versão; com chaves do Langfuse no `.env`, cada eval publica o golden como dataset e cada variante ou execução como run com os scores por item.

Cada rodada completa é gravada como uma Execução na tabela `execucoes_de_eval` (`execucoes.py`), com o contexto (modelos, versões dos prompts, variante no ar), os números de destaque e cada caso, e é isso que a Tela de Avaliação (`/avaliacao`) projeta; `--sem-salvar` roda sem gravar, e rodadas parciais (`--amostra N`) nunca são gravadas. Em produção, rode de dentro do worker do Railway, que enxerga o banco e tem as chaves dos modelos: `railway ssh --service worker -- ampere-evals agente`. A aba Dados da tela mostra os três goldens, lidos destes mesmos CSVs por `conjuntos.py`, com os ids e grupos das execuções e, no juiz, o conjunto de cada rótulo (treino, dev ou teste) pela mesma divisão da calibração. A tela também dispara uma amostra ao vivo de 3 casos sorteados de grupos diferentes (`ao_vivo.py`): um job `eval` na mesma fila do chat, que roda cada caso soltando o nome de cada fase (os nós do grafo, no agente) e grava cada caso antes de avisar. O RAG completo em produção gasta a cota da Groq que o trabalhador do chat usa, então rode com folga antes da aula.

Como rodar, a partir de `backend/`, com Qdrant ingerido (`uv run ampere ingest --todas`) e as chaves no `.env`:

```bash
uv run ampere-evals rag                  # todas as variantes; geração + juiz só na variante do .env
uv run ampere-evals rag --so-retrieval   # só Recall@5 e MRR, sem gastar gerador nem juiz
uv run ampere-evals rag --amostra 10     # as 10 primeiras perguntas
uv run ampere-evals agente               # um turno por cenário, tabela por dimensão e veredito
uv run ampere-evals agente --amostra 5
uv run ampere-evals agente --sem-salvar  # roda sem gravar a execução no banco
uv run ampere-evals calibracao           # TPR, TNR, matriz, desacordos e Rogan-Gladen com IC
```
