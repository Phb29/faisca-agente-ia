"""Mascaramento por expressão regular de cartão, CPF e senha antes de gravar em memória."""

import re

# 13 a 19 dígitos, cada um possivelmente separado por um espaço ou hífen.
CARTAO = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
# ddd.ddd.ddd-dd ou 11 dígitos contíguos.
CPF = re.compile(r"(?<!\d)(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?!\d)")
# "senha" seguida de ":", "=" ou "é" e um valor sem espaço (pontuação final fica de fora).
SENHA = re.compile(r"\bsenha\s*(?::|=|é)\s*(\S+?)(?=[,.;]*(?:\s|$))", re.IGNORECASE)


def mascarar(texto: str) -> str:
    """Substitui cartão, CPF e senha por marcadores; texto sem nada sensível volta igual."""
    texto = CPF.sub("[CPF MASCARADO]", texto)
    texto = CARTAO.sub("[CARTÃO MASCARADO]", texto)
    return SENHA.sub("senha: [SENHA MASCARADA]", texto)
