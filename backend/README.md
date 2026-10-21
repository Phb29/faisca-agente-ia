# Backend

Backend Python do chatbot da Ampère, organizado por conceito de domínio (ver `docs/adr/0005`). Cada pasta de `ampere/` corresponde a um termo do glossário em `CONTEXT.md` e tem um README de um parágrafo. O grafo importa das outras pastas; nenhuma outra importa do grafo, e `prompts/` e `regras/` não importam de ninguém. Quem liga tudo é `ampere/composicao.py`. As duas regras são verificadas por `tests/unit/test_arquitetura.py`.

Como rodar os testes: `uv sync` e `uv run pytest`, daqui de dentro. Para subir o sistema, siga o README da raiz: os comandos `ampere` rodam da raiz, com `uv run --project backend ampere ...`, para lerem o `.env` de lá. Unitários e o teste do grafo não precisam de nada; os de integração rodam quando `DATABASE_URL` e `QDRANT_URL` apontam para o docker-compose e pulam sozinhos quando não.
