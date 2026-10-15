"""Mascaramento de cartão, CPF, CVV e senha por expressão regular.

É a camada determinística da proteção de dado sensível: a API mascara cada mensagem do
Cliente antes de gravar qualquer coisa (transcript, fila, checkpoint, trace), e o Guardrail
de entrada mascara de novo dentro do grafo. Texto sem nada sensível volta igual, então
aplicar duas vezes não muda nada.
"""

import re

# 13 a 19 dígitos, cada um possivelmente separado por um espaço ou hífen.
CARTAO = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
# ddd.ddd.ddd-dd ou 11 dígitos seguidos.
CPF = re.compile(r"(?<!\d)(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?!\d)")
# "cvv", "cvc" ou "código de segurança", talvez com "é", ":" ou "=", e 3 ou 4 dígitos.
CVV = re.compile(
    r"\b(cvv|cvc|c[óo]digo\s+de\s+seguran[çc]a)(\s*(?:é|:|=)?\s*)\d{3,4}\b", re.IGNORECASE
)
# "senha" seguida de ":", "=" ou "é" e um valor sem espaço (a pontuação final fica de fora);
# um valor que já é marcador ("[SENHA MASCARADA]") não é mascarado de novo.
SENHA = re.compile(r"\bsenha\s*(?::|=|é)\s*(?!\[)(\S+?)(?=[,.;]*(?:\s|$))", re.IGNORECASE)


def mascarar(texto: str) -> str:
    texto = CPF.sub("[CPF MASCARADO]", texto)
    texto = CARTAO.sub("[CARTÃO MASCARADO]", texto)
    texto = CVV.sub(r"\1\2[CVV MASCARADO]", texto)
    return SENHA.sub("senha: [SENHA MASCARADA]", texto)
