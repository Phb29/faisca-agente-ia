# Suporte Ampère

Chatbot de suporte ao cliente de um e-commerce fictício de eletrônicos chamado Ampère. Serve de base para um workshop ao vivo que disseca uma solução de engenharia de IA em produção.

## Language

**Loja**:
O e-commerce fictício de eletrônicos (Ampère Eletrônicos) que o chatbot atende.
_Avoid_: Empresa, cliente (no sentido de quem contrata o bot)

**Cliente**:
A pessoa que compra na Loja e conversa com o chatbot.
_Avoid_: Usuário, consumidor

**Base de Conhecimento**:
O conjunto de políticas da Loja (troca, devolução, frete, garantia, pagamento, cadastro) que o chatbot consulta para responder.
_Avoid_: Documentos, corpus, FAQ

**Guardrail**:
Verificação rápida feita pelo Jev na entrada (mensagem do Cliente) ou na saída (resposta do chatbot) que pode bloquear ou redirecionar a conversa.
_Avoid_: Filtro, validação, moderação

**Regra**:
Uma pergunta que o Jev responde para decidir algo (um Guardrail, o Roteador ou o Gate de Aprovação), escrita em linguagem natural com quando a resposta é sim, quando é não e o que acontece quando ela dispara.
_Avoid_: Policy, prompt do Jev, critério

**Roteador**:
Decisão do Jev sobre a intenção da mensagem do Cliente, que define qual caminho do grafo será seguido.
_Avoid_: Classificador, intent detector

**Gate de Aprovação**:
Decisão do Jev sobre se uma ação do chatbot é crítica o bastante para exigir aprovação humana antes de executar.
_Avoid_: Checkpoint, revisão, HITL

**Conversa**:
A troca de mensagens entre um Cliente e o chatbot, identificada por um único thread.
_Avoid_: Sessão, chat, atendimento

**Ticket**:
Registro criado quando o chatbot não consegue resolver a Conversa e a entrega a um atendente humano, com resumo, categoria e prioridade.
_Avoid_: Chamado, caso, escalação (como substantivo)

**Resolver**:
Encerrar a Conversa com a necessidade do Cliente atendida sem criar um Ticket.
_Avoid_: Finalizar, fechar

**Escalar**:
Criar um Ticket e encerrar a participação do chatbot na Conversa, porque o Cliente pediu uma pessoa ou porque o Guardrail de saída reprovou a resposta duas vezes.
_Avoid_: Transferir, encaminhar

**Ação**:
Uma das quatro operações que o chatbot pode executar: consultar Pedido, consultar Base de Conhecimento, emitir Reembolso, abrir Ticket.
_Avoid_: Tool, ferramenta, função

**Pedido**:
Uma compra feita pelo Cliente na Loja, identificada por número.
_Avoid_: Compra, ordem, order

**Reembolso**:
Devolução de dinheiro ao Cliente referente a um Pedido. É a única Ação crítica e passa pelo Gate de Aprovação.
_Avoid_: Estorno, devolução (que é do produto, não do dinheiro)

## Memória

**Memória de Curto Prazo**:
O estado de uma única Conversa, incluindo as mensagens trocadas e um resumo das mais antigas quando ela fica longa.
_Avoid_: Histórico, contexto da sessão

**Memória Semântica**:
Fatos duradouros sobre um Cliente, extraídos ao fim de cada Conversa e recuperados por similaridade no início da próxima.
_Avoid_: Perfil, preferências (que são Memória Procedural)

**Memória Episódica**:
O resumo de uma Conversa passada de um Cliente, com o desfecho (Resolvida ou Escalada) e as Ações tomadas.
_Avoid_: Log, histórico de atendimentos

**Memória Procedural**:
Instruções de como atender um Cliente específico, aplicadas ao comportamento do chatbot em toda Conversa futura.
_Avoid_: Regras, preferências, configuração do cliente

## Pessoas e aprovação

**Atendente**:
Funcionário da Loja que aprova ou rejeita Reembolsos pendentes e recebe os Tickets escalados.
_Avoid_: Operador, humano, revisor, agente (reservado ao chatbot)

**Aprovação Pendente**:
Um Reembolso que o Gate de Aprovação retirou do fluxo automático e que aguarda decisão do Atendente, com a Conversa congelada.
_Avoid_: Interrupt, checkpoint, pedido de revisão

**Tela do Atendente**:
A página onde o Atendente vê as Aprovações Pendentes, os Tickets e edita a Memória Procedural de cada Cliente.
_Avoid_: Painel, dashboard, admin

## Acesso

**Sessão**:
O período em que o navegador está autenticado depois do login, válido por 12 horas e guardado no Postgres pelo hash do token, nunca pelo token em si. Protege o chat, a Central do Atendente e a Tela de Avaliação.
_Avoid_: Conversa (que é a troca de mensagens com o chatbot), token, cookie

## Avaliação

**Execução**:
Uma rodada de um eval (Busca, Agente ou Juiz): completa, com o golden inteiro, rodada pelo terminal antes da aula, ou amostra, com 3 casos sorteados, rodada na frente da turma.
_Avoid_: Run, experimento, rodada de teste

**Amostra ao vivo**:
A Execução de 3 casos sorteados de grupos diferentes, disparada pela Tela de Avaliação e rodada pela mesma fila do chat.
_Avoid_: Demo, preview, teste rápido

**Tela de Avaliação**:
A página que projeta as Execuções dos três evals com números grandes e dispara a Amostra ao vivo, protegida pela Sessão de login (ADR 0010).
_Avoid_: Dashboard de evals, painel de métricas
