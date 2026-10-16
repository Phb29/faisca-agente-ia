"""Hash de senha com scrypt: gera e confere, recusa senha errada e hash estragado, e o formato
não tem `$`, para não sofrer interpolação no `.env`. Quantos scrypt rodam juntos é a rota de
login que decide (ver tests/integracao/test_acesso.py)."""

import pytest

from ampere.acesso.senha import HASH_FIXO, conferir, gerar_hash


def test_gera_e_confere():
    hash_ = gerar_hash("correto cavalo bateria grampo")

    assert conferir("correto cavalo bateria grampo", hash_)


def test_senha_errada_nao_confere():
    hash_ = gerar_hash("correto cavalo bateria grampo")

    assert not conferir("correto cavalo bateria grampa", hash_)
    assert not conferir("", hash_)


def test_cada_hash_tem_sal_proprio():
    assert gerar_hash("mesma senha") != gerar_hash("mesma senha")


def test_formato_sem_cifrao_e_com_os_parametros():
    hash_ = gerar_hash("senha")

    assert "$" not in hash_
    assert "=" not in hash_
    nome, n, r, p, sal, derivado = hash_.split(":")
    assert (nome, n, r, p) == ("scrypt", "32768", "8", "1")
    assert sal and derivado


@pytest.mark.parametrize(
    "estragado",
    [
        "",
        "texto qualquer",
        "bcrypt:32768:8:1:c2Fs:aGFzaA",
        "scrypt:32768:8:1:c2Fs",
        "scrypt:nao:8:1:c2Fs:aGFzaA",
        "scrypt:1000:8:1:c2Fs:aGFzaA",
        "scrypt:-1:8:1:c2Fs:aGFzaA",
        "scrypt:32768:8:1:%%%:aGFzaA",
        "scrypt:32768:8:1:c2Fs:",
        "scrypt:" + "9" * 400 + ":8:1:c2Fs:aGFzaA",
        "$scrypt$32768$8$1$c2Fs$aGFzaA",
    ],
)
def test_hash_malformado_devolve_false(estragado):
    assert conferir("senha", estragado) is False


def test_hash_fixo_tem_o_custo_padrao_e_nao_confere_com_nada_obvio():
    assert HASH_FIXO.startswith("scrypt:32768:8:1:")
    assert not conferir("", HASH_FIXO)
    assert not conferir("senha", HASH_FIXO)
