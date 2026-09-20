"""Mascaramento de dado sensível antes de qualquer gravação em memória."""

from ampere.guardrails.mascaramento import mascarar


def test_mascara_cartao_com_espacos():
    assert mascarar("meu cartão é 4111 1111 1111 1111 ok") == "meu cartão é [CARTÃO MASCARADO] ok"


def test_mascara_cartao_com_hifens_e_contiguo():
    assert mascarar("4111-1111-1111-1111") == "[CARTÃO MASCARADO]"
    assert mascarar("cartão 4111111111111111") == "cartão [CARTÃO MASCARADO]"


def test_mascara_cartao_de_13_e_19_digitos():
    assert mascarar("4111111111111") == "[CARTÃO MASCARADO]"
    assert mascarar("4111 1111 1111 1111 111") == "[CARTÃO MASCARADO]"


def test_mascara_cpf_formatado_e_contiguo():
    assert mascarar("meu CPF é 123.456.789-09") == "meu CPF é [CPF MASCARADO]"
    assert mascarar("cpf 12345678909 aqui") == "cpf [CPF MASCARADO] aqui"


def test_mascara_senha_com_dois_pontos_igual_e_verbo():
    assert mascarar("minha senha: abc123") == "minha senha: [SENHA MASCARADA]"
    assert mascarar("senha=abc123") == "senha: [SENHA MASCARADA]"
    assert mascarar("a senha é abc123, ok?") == "a senha: [SENHA MASCARADA], ok?"
    assert mascarar("Senha: X1!") == "senha: [SENHA MASCARADA]"


def test_texto_sem_nada_sensivel_volta_igual():
    texto = "Meu pedido 12345 chegou com defeito, quero trocar. Telefone 11 98765-4321."
    assert mascarar(texto) == texto


def test_mascara_varios_dados_no_mesmo_texto():
    texto = "cpf 123.456.789-09, cartão 4111 1111 1111 1111 e senha: seg"
    esperado = "cpf [CPF MASCARADO], cartão [CARTÃO MASCARADO] e senha: [SENHA MASCARADA]"
    assert mascarar(texto) == esperado
