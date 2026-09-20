# Backend organizado por conceito de domínio, não por camada

Cada pasta do backend corresponde a um termo do glossário (grafo, rag, memoria, guardrails, roteador, acoes, fila, api, observabilidade, evals) e tem um README de um parágrafo. A organização por camada (routers, services, repositories) foi rejeitada porque espalha cada conceito em três lugares e prejudica o objetivo didático do projeto. Regra de acoplamento: o grafo importa das outras pastas, e nenhuma outra pasta importa do grafo.
