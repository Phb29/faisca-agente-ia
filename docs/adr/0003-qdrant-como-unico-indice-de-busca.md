# Qdrant como único índice de busca, uma coleção por variante

A busca híbrida inteira (denso MiniLM, esparso BM25 via fastembed com IDF do Qdrant, fusão RRF e rerank ColBERT MaxSim) roda numa única chamada da Query API do Qdrant, em vez de ser montada em Python. Postgres com pgvector foi rejeitado porque não faz BM25 nem multivetor nativamente e obrigaria a manter índices em memória. Cada combinação de modelo de embedding e estratégia de chunking é uma coleção separada (as dimensões diferem), o que permite ao eval de RAG comparar variantes lado a lado sem reindexar.
