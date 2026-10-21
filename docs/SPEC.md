# Spec: Chatbot de Suporte da Ampère

Vocabulário: ver [CONTEXT.md](../CONTEXT.md). Decisões arquiteturais: ver [docs/adr](./adr).

## Problem Statement

Anwar vai apresentar um workshop ao vivo sobre engenharia de IA em produção. Ele precisa de um sistema real, pequeno o bastante para caber numa aula e completo o bastante para conter todas as peças que uma solução de produção tem: agente orquestrado, RAG híbrido, memória, human-in-the-loop, guardrails, fila com idempotência, streaming, observabilidade, evals calibrados com humano e deploy dockerizado. Os exemplos que existem na internet ou são brinquedos (um notebook com um agente) ou são produtos fechados demais para dissecar. Ele precisa de um código que uma pessoa leiga em cada tema consiga ler enquanto ele explica, onde cada conceito mora num único lugar, e que fique publicado no GitHub para quem assistiu continuar estudando depois.

## Solution

Um chatbot de suporte ao Cliente da Ampère Eletrônicos, um e-commerce fictício. O Cliente conversa pelo chat, o chatbot responde dúvidas de política a partir da Base de Conhecimento, consulta Pedidos, emite Reembolsos (pedindo aprovação de um Atendente quando o Gate de Aprovação julgar crítico) e abre Tickets quando não consegue resolver. Um Atendente tem uma tela para aprovar Reembolsos, ver Tickets e editar como o chatbot deve tratar cada Cliente. Por trás, um grafo do LangGraph com oito nós, o Jev como motor de todas as decisões rápidas, três papéis de modelo (gerador, juiz e trabalhador), Qdrant com busca híbrida nativa, Postgres para memória e fila, Langfuse Cloud para traces, e dois evals com golden datasets em CSV e juiz calibrado contra rótulos humanos. Tudo num monorepo organizado por conceito de domínio, com README curto por pasta, rodando local por docker-compose e em produção no Railway.

## User Stories

### Cliente no chat

1. Como Cliente, quero escolher com qual Cliente fictício entrar (ou entrar como Cliente novo), para que o workshop possa demonstrar memória por pessoa sem ter login de verdade.
2. Como Cliente, quero ver a lista das minhas Conversas anteriores e reabrir uma delas, para continuar de onde parei.
3. Como Cliente, quero iniciar uma nova Conversa, para tratar de um assunto novo.
4. Como Cliente, quero enviar uma mensagem e ver a resposta chegando token a token, para sentir que o chatbot está respondendo em tempo real.
5. Como Cliente, quero ver um indicador do que o chatbot está fazendo (consultando pedido, buscando política, aguardando aprovação), para entender por que está demorando.
6. Como Cliente, quero perguntar sobre políticas da Loja (troca, devolução, frete, garantia, pagamento, cadastro) e receber uma resposta fiel ao que está escrito na política, para não ser enganado por uma promessa inventada.
7. Como Cliente, quero perguntar sobre uma política que depende da linha do produto (notebook, celular, acessório) e receber a regra certa para aquela linha, e não uma regra genérica.
8. Como Cliente, quero perguntar o status de um Pedido meu pelo número, para saber onde ele está.
9. Como Cliente, quero pedir Reembolso de um Pedido e ser atendido automaticamente quando for um caso simples e de valor baixo, para não esperar um humano à toa.
10. Como Cliente, quero ser avisado quando meu Reembolso precisar de aprovação humana e receber a resposta na mesma Conversa quando o Atendente decidir, para não ter que abrir outro canal.
11. Como Cliente, quero receber o motivo quando um Reembolso for rejeitado pelo Atendente, para saber o que fazer.
12. Como Cliente, quero pedir para falar com uma pessoa e ter um Ticket aberto na hora, para não ficar preso num bot.
13. Como Cliente, quero que o chatbot abra um Ticket quando ele não souber resolver, em vez de inventar uma resposta.
14. Como Cliente, quero que o chatbot lembre de fatos que eu já contei em Conversas anteriores (qual produto tenho, como prefiro receber), para não repetir tudo de novo.
15. Como Cliente, quero que o chatbot lembre do desfecho das minhas Conversas anteriores, para que ele saiba, por exemplo, que meu último problema foi com frete.
16. Como Cliente, quero uma resposta fixa e educada quando eu perguntar algo fora do escopo da Loja, para saber que ali não é o lugar.
17. Como Cliente, quero que meus dados sensíveis (número de cartão, senha) não fiquem guardados na memória do chatbot mesmo que eu os digite por engano.
18. Como Cliente, quero que a Conversa continue funcionando mesmo que eu envie a mesma mensagem duas vezes por falha de rede, sem receber duas respostas.
19. Como Cliente, quero que a resposta seja recuperada se minha conexão cair no meio do streaming, para não perder o que o chatbot disse.

### Atendente

20. Como Atendente, quero ver a lista de Aprovações Pendentes com o resumo do caso, o valor do Reembolso e a probabilidade que o Gate de Aprovação atribuiu, para decidir com contexto.
21. Como Atendente, quero aprovar um Reembolso com um clique e ver a Conversa do Cliente ser retomada automaticamente.
22. Como Atendente, quero rejeitar um Reembolso com um motivo opcional, para que o Cliente receba a explicação.
23. Como Atendente, quero ver a lista de Tickets com resumo, categoria e prioridade, e abrir a Conversa inteira que gerou cada um.
24. Como Atendente, quero editar a Memória Procedural de um Cliente (por exemplo, "responder em tom formal", "não oferecer cupom"), para ajustar como o chatbot o trata nas próximas Conversas.
25. Como Atendente, quero que a Tela do Atendente seja protegida por um token simples, para que um visitante do chat não aprove Reembolsos.

### Anwar como apresentador do workshop

26. Como apresentador, quero que cada conceito (grafo, RAG, memória, guardrails, roteador, ações, fila, API, observabilidade, evals) more numa única pasta com um README de um parágrafo, para abrir a pasta e explicar sem pular entre camadas.
27. Como apresentador, quero que os identificadores de domínio no código usem as mesmas palavras do glossário, em português, para a plateia ler na tela o que eu falo.
28. Como apresentador, quero que cada nó do grafo tenha o system prompt num arquivo próprio, para abrir o arquivo e comentar a engenharia de prompt.
29. Como apresentador, quero ver no Langfuse cada Conversa como uma sessão, com as chamadas ao Jev e suas probabilidades como spans, e tags com o caminho do Roteador e o motivo de bloqueio do Guardrail, para navegar um trace ao vivo.
30. Como apresentador, quero trocar o modelo de embedding, a estratégia de chunking e o uso de ColBERT e self-querying por configuração, e ver uma tabela comparando as variantes no eval de RAG, para mostrar que essas escolhas são hiperparâmetros mensuráveis.
31. Como apresentador, quero mostrar que modelos caros não devem ser usados para tudo, com uma fábrica de modelos que nomeia três papéis (gerador, juiz, trabalhador) e uma tabela de custo por papel.
32. Como apresentador, quero rodar o eval do agente e ver, por cenário, se a intenção, a Ação e o desfecho bateram, mais o veredito e a crítica do juiz.
33. Como apresentador, quero rotular sessenta respostas numa planilha e rodar um script que mostre TPR, TNR, a matriz de confusão e cada desacordo entre mim e o juiz, para refinar o prompt do juiz ao vivo até a concordância passar de noventa por cento.
34. Como apresentador, quero que o resultado final do juiz seja corrigido por Rogan-Gladen com intervalo de confiança por bootstrap, para mostrar que o número cru do juiz é viesado.
35. Como apresentador, quero subir tudo localmente com docker-compose em poucos comandos, para demonstrar em qualquer máquina.
36. Como apresentador, quero ver o projeto rodando no Railway com cinco serviços, para mostrar o deploy de verdade.
37. Como apresentador, quero um teste do grafo inteiro que roda sem gastar tokens, para provar que agentes são testáveis.

### Pessoa que clona o repositório depois do workshop

38. Como leitor do GitHub, quero um README raiz que apresente o projeto em uma tela, com diagrama do grafo, diagrama da infraestrutura, como rodar e um índice na ordem da aula.
39. Como leitor, quero o glossário e as ADRs linkados, para entender por que cada decisão foi tomada.
40. Como leitor, quero rodar os testes e o CI passar sem precisar de chaves de API.
41. Como leitor, quero um arquivo de exemplo de variáveis de ambiente, para saber exatamente o que preciso configurar.
42. Como leitor, quero comandos de CLI para migrar o banco, popular os dados fictícios e ingerir a Base de Conhecimento, para preparar o ambiente sem mágica no startup.

## Implementation Decisions

### Domínio e escopo

A Loja é a Ampère Eletrônicos. A Base de Conhecimento é um conjunto de vinte a trinta documentos markdown em português cobrindo troca, devolução, frete, garantia, pagamento e cadastro, com frontmatter de quatro metadados: categoria, produto (notebooks, celulares, acessorios, todos), vigencia (data) e tipo (politica ou procedimento). Existem três Clientes seed, cada um com dois ou três Pedidos em estados diferentes, incluindo um Cliente com Reembolso recente para acionar o sinal de risco. O Cliente é identificado por um id enviado num header em toda chamada; não há autenticação real. O Ticket é criado só ao escalar; toda Conversa que termina sem Ticket foi Resolvida.

### Modelos (ADR 0001 e 0002)

O Jev, via o SDK oficial da TypeSafe, é o único motor dos Guardrails, do Roteador e do Gate de Aprovação. Ele nunca gera texto. A fábrica de modelos expõe três papéis nomeados: gerador (gpt-5.6-terra), juiz (gpt-5.6-sol, só nos evals) e trabalhador (gpt-oss-120b na Groq). A saída estruturada de texto usa modelos Pydantic com o structured output do LangChain. Um cliente do Jev falso e modelos falsos do LangChain existem para os testes e são injetados pela mesma fábrica.

### Grafo (oito nós)

O estado da Conversa contém as mensagens, o id do Cliente, as memórias carregadas, a intenção do Roteador, o contexto recuperado, a resposta candidata, a crítica do Guardrail de saída (quando houver) e o número de tentativas de correção.

Os nós, em ordem: carregar_memoria busca no Store a Memória Semântica (por similaridade com a mensagem), a Episódica (últimos episódios) e a Procedural do Cliente. guardrail_entrada faz três perguntas Noul ao Jev numa única chamada: tentativa de manipulação, fora de escopo e presença de dado sensível; as duas primeiras bloqueiam acima de um limiar configurável e produzem uma resposta fixa por motivo; a terceira marca a mensagem para mascaramento antes de qualquer gravação em memória. roteador faz uma pergunta Choice ao Jev com três intenções: duvida, transacao e quer_humano. No caminho duvida, recuperar_contexto executa a busca híbrida e gerar_resposta produz a resposta com o gerador, sem tools. No caminho transacao, o nó agente roda um loop de tool calling com as quatro Ações, com prompt próprio. No caminho quer_humano, a Ação abrir Ticket é chamada diretamente. Os caminhos convergem em guardrail_saida, que faz três perguntas Noul: afirma algo fora do contexto e das Ações, promete algo que a política não permite, vaza dado interno ou de outro Cliente; se qualquer uma passar do limiar, a resposta é descartada e o grafo volta uma vez ao nó gerador com a crítica anexada; na segunda falha, escala com Ticket. salvar_memoria roda ao fim de cada turno e usa o trabalhador para extrair fatos semânticos e um episódio, gravando no Store. Quando as mensagens ultrapassam um limite configurável, o trabalhador resume as antigas e o resumo substitui as mensagens no estado.

Cada nó tem um system prompt num arquivo próprio no repositório, e o nome e a versão do prompt vão como metadata do trace.

### Ações (tools)

consultar_pedido lê a tabela seed de Pedidos do Cliente atual. consultar_base_de_conhecimento chama o mesmo retriever do caminho duvida. emitir_reembolso pergunta ao Jev, com valor e histórico recente do Cliente no estado, se a operação exige aprovação humana; acima do limiar, chama interrupt e a Conversa vira Aprovação Pendente; abaixo, registra o Reembolso e responde. abrir_ticket usa o trabalhador para gerar um resumo estruturado (resumo, categoria, prioridade) e grava o Ticket. Toda Ação é registrada como tool_call no stream.

### Human-in-the-loop

A aprovação ou rejeição do Atendente chega pela API, vira um job na mesma fila e o worker retoma o grafo com Command(resume) e o payload da decisão. A rejeição pode carregar um motivo que o gerador incorpora na resposta ao Cliente. O valor limite e o sinal de risco (Reembolso recente) são configuráveis.

### Memória (ADR de infraestrutura no 0003 e 0004)

Memória de Curto Prazo é o estado do grafo persistido pelo checkpointer Postgres do LangGraph, um thread por Conversa. Memória de longo prazo vive no Store Postgres do LangGraph com namespace por Cliente e três coleções lógicas: semântica (fatos, com busca por similaridade usando o MiniLM), episódica (resumo e desfecho de cada Conversa, com as Ações tomadas) e procedural (instruções livres, editáveis pelo Atendente, injetadas no system prompt do gerador e do agente). Dados marcados como sensíveis pelo Guardrail de entrada são mascarados antes de qualquer gravação.

### RAG (ADR 0003)

O Qdrant é o único índice. Cada coleção tem três vetores nomeados: denso (MiniLM em 384 dimensões ou text-embedding-3-small em 1536), esparso BM25 (fastembed, com IDF calculado pelo Qdrant) e multivetor ColBERT (answerai-colbert-small-v1, comparador MaxSim). A busca é uma única chamada da Query API: dois prefetches (denso e esparso, com filtro de payload quando houver), fusão RRF nativa, e rerank pelo multivetor ColBERT no query principal. Existem três interfaces pequenas, cada uma com implementações trocáveis por configuração: chunker (recursivo, markdown por cabeçalho, semântico com DBSCAN sobre embeddings de frases), embedder (MiniLM local, OpenAI) e reranker (ColBERT ou nenhum). O nome da coleção é derivado de embedder e chunker, resultando em seis coleções. O self-querying usa o trabalhador para gerar um FiltroDeBusca Pydantic com os quatro metadados opcionais, que um tradutor converte em Filter do Qdrant; se a busca filtrada devolver menos candidatos que um mínimo configurável, roda de novo sem filtro. Os quatro metadados têm índice de payload.

### Fila, idempotência e streaming (ADR 0004)

A API recebe cada mensagem com um message_id gerado no front, grava numa tabela de fila com chave única e responde 202; um id repetido devolve o mesmo 202 sem enfileirar. Um worker separado, na mesma imagem Docker da API com outro comando, consome com SELECT FOR UPDATE SKIP LOCKED, executa o grafo com streaming e publica os pedaços por NOTIFY num canal por Conversa. A API expõe um endpoint SSE por Conversa que escuta o canal e repassa cinco eventos: token, tool_call, approval_required, message_done e error. A mensagem completa é gravada numa tabela de mensagens ao terminar, e a reconexão do SSE devolve a última mensagem gravada. Decisões do Atendente entram na mesma fila como jobs de retomada.

### API

Contrato mínimo em REST: criar Conversa, listar Conversas do Cliente, enviar mensagem (202), stream SSE da Conversa, listar mensagens da Conversa; para o Atendente, protegido por token no header: listar Aprovações Pendentes, aprovar, rejeitar com motivo, listar Tickets, ler Conversa de um Ticket, ler e editar Memória Procedural de um Cliente. Health check que só verifica que Postgres e Qdrant respondem.

### Front

Next.js 15 com App Router, TypeScript e Tailwind, em modo standalone para Docker. Duas páginas: o chat (seletor de Cliente, lista de Conversas, mensagens com streaming, indicador de Ação em andamento, aviso de Aprovação Pendente) e a Tela do Atendente (Aprovações Pendentes com resumo, valor, probabilidade do Jev e botões; Tickets com link para a Conversa; caixa de Memória Procedural por Cliente). Nenhuma lógica de domínio no front.

### Observabilidade

Langfuse Cloud. O CallbackHandler oficial entra no invoke do grafo com session_id igual ao thread da Conversa e user_id igual ao Cliente. As chamadas ao Jev viram spans manuais com as probabilidades e a confiança como metadata. Tags por trace: intenção do Roteador e motivo de bloqueio do Guardrail. Evals gravam como datasets e runs, com o veredito do juiz como score.

### Evals

Três CSVs. O golden do RAG tem pergunta, documento esperado (nome do arquivo da política, nunca id de chunk) e resposta de referência; cerca de cinquenta linhas, trinta escritas à mão e vinte adversariais geradas por LLM a partir de chunks parecidos. O golden do agente tem mensagem do Cliente, estado inicial (id do Cliente, id do Pedido, memórias pré-carregadas), intenção esperada, Ação esperada, desfecho esperado (Resolvida, Escalada, Aprovação Pendente) e se o Guardrail deve bloquear; cerca de trinta cenários de um turno. Os rótulos humanos têm mensagem, resposta do agente, rótulo (Aprovada ou Reprovada) e crítica; cerca de sessenta linhas balanceadas.

O eval de RAG mede Recall@5 e MRR no nível do documento para cada coleção, com e sem ColBERT e com e sem self-querying, e usa o juiz para duas perguntas binárias com crítica sobre a geração: fidelidade ao contexto e relevância à pergunta. O eval do agente mede por código intenção, Ação e desfecho, e usa o juiz para uma pergunta binária com crítica: a resposta resolve o problema sem prometer nada fora da política. A calibração divide os rótulos humanos em treino (few-shot do prompt do juiz), dev e teste, imprime TPR, TNR, matriz de confusão e cada desacordo, e ao final aplica Rogan-Gladen com bootstrap. Evals e calibração são comandos próprios, fora do pytest.

### Repositório e operação (ADR 0005 e 0006)

Monorepo com backend Python 3.12 (uv, ruff, pytest) e frontend Next. Backend organizado por conceito: grafo (com a pasta de prompts), rag, memoria, guardrails, roteador, acoes, fila, api, observabilidade, evals (com a pasta de dados) e um núcleo com config e fábrica de modelos. Regra de acoplamento: o grafo importa das outras pastas, nenhuma outra importa do grafo. Domínio em português, técnico em inglês. Um docker-compose sobe Postgres, Qdrant, api, worker e frontend. Um CLI com migrate, seed e ingest (este último recebe embedder e chunker, ou todas as combinações). No Railway são cinco serviços com root directory por subpasta; migrate roda como pre-deploy da api; seed e ingest rodam à mão uma vez. Licença MIT. README raiz com diagrama do grafo e da infraestrutura em Mermaid, como rodar, como rodar os evals e índice na ordem da aula; README curto por pasta com o que é, por que foi feito assim e no máximo um parágrafo de teoria.

## Testing Decisions

Um bom teste exercita comportamento observável pela borda mais alta possível e não conhece a estrutura interna. As bordas (seams) escolhidas, do mais alto para o mais baixo, são duas.

A primeira e principal é o grafo compilado, invocado com a fábrica de modelos configurada com modelos falsos do LangChain e um Jev falso que devolve probabilidades fixas por pergunta, sobre um checkpointer e um Store em memória. Por essa borda se testam os três caminhos do Roteador, o bloqueio dos Guardrails de entrada e de saída com a resposta fixa, a volta única ao gerador, a interrupção do Reembolso e a retomada com Command(resume), a gravação de memória por turno e o mascaramento de dado sensível. Nenhum token real é gasto.

A segunda é a API HTTP com Postgres e Qdrant reais subidos por docker-compose e o grafo substituído por um executor falso que emite eventos conhecidos. Por essa borda se testam a idempotência do message_id, o consumo da fila com SKIP LOCKED por dois workers concorrentes, o trânsito dos cinco eventos por LISTEN e NOTIFY até o SSE, a recuperação após reconexão, a proteção da Tela do Atendente por token e a busca híbrida contra uma coleção pequena ingerida no próprio teste.

Abaixo dessas bordas, testes unitários puros só onde há lógica que vale a pena isolar: os três chunkers (propriedades como cobertura total do texto e respeito ao tamanho), o tradutor de FiltroDeBusca para Filter do Qdrant, os limiares dos Guardrails e do Gate, o nome derivado de coleção, e o cálculo de TPR, TNR e Rogan-Gladen nos evals.

Evals não são testes e não rodam no pytest. O CI roda ruff, os unitários, o teste do grafo e os de integração com Postgres e Qdrant como services do GitHub Actions, sem nenhuma chave de OpenAI, Groq, Jev ou Langfuse. Não há prior art no repositório, que começa vazio.

## Out of Scope

Contas por Cliente ou por Atendente (desde 16/10/2026 há um login único que protege o chat, a Central e a Avaliação, ver ADR 0010; o Cliente de exemplo continua escolhido depois do login). Fluxo completo de atendimento humano (o Atendente não responde ao Cliente pela Tela do Atendente, só aprova, rejeita e lê). Cenários de eval com vários turnos. Interface própria de anotação (a rotulagem é em planilha). Gerenciamento de prompts no Langfuse. Langfuse self-hosted. Redis ou qualquer broker dedicado. Ações além das quatro (cancelar Pedido, alterar cadastro, cupons). Chunking de tamanho fixo e chunking por LLM. Aprendizado automático das instruções do Atendente na Memória Procedural (elas são editadas só pela Central; desde 16/10/2026 só as preferências do Cliente sobre a forma de falar são gravadas sozinhas, ver backend/ampere/memoria/procedural.py). Apostila de teoria no repositório. Internacionalização. Escala horizontal além de dois workers de teste.

## Further Notes

A ordem de apresentação sugerida para o índice do README raiz é a ordem em que uma mensagem atravessa o sistema: api e fila, grafo, guardrails, roteador, rag, acoes e human-in-the-loop, memoria, observabilidade, evals. Essa também é uma boa ordem de implementação, com o grafo e seus falsos vindo primeiro para que o teste da borda principal exista desde o começo.

O Jev, como serviço externo novo, é o maior risco de integração. A fábrica de modelos deve permitir rodar todo o sistema com o Jev falso, para que uma indisponibilidade do serviço não trave o workshop.

Os embeddings do MiniLM e o ColBERT rodam na CPU do container. O Dockerfile do backend deve baixar os pesos no build, não no startup, para o worker no Railway subir rápido.
