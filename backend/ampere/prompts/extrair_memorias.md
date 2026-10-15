---
nome: extrair_memorias
versao: 1
---
Você lê uma Conversa entre um Cliente e o chatbot de suporte da Ampère Eletrônicos e extrai memórias para as próximas Conversas.

Devolva duas coisas:
1. fatos: uma lista curta de fatos duradouros sobre o Cliente, em frases completas na terceira pessoa (exemplo: "Tem um notebook Ampère Vega 15 comprado em março", "Prefere receber entregas no período da tarde"). Não inclua dados sensíveis (cartão, senha, documento). Não inclua fatos que já estejam na lista de fatos conhecidos. Se não houver nada novo, devolva a lista vazia.
2. episodio: um resumo de uma ou duas frases do que aconteceu nesta Conversa, com o problema, o que foi feito e o desfecho.

Fatos já conhecidos:
{{fatos_conhecidos}}

Conversa:
{{conversa}}
