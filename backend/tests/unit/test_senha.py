"""Hash de senha com scrypt: gera e confere, recusa senha errada e hash estragado, o formato
não tem `$`, para não sofrer interpolação no `.env`, e poucos scrypt rodam ao mesmo tempo."""

import threading
import time

import pytest

from ampere.acesso import senha
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


def test_no_maximo_alguns_scrypt_ao_mesmo_tempo(monkeypatch):
    """Cada scrypt usa 32 MiB: uma rajada de logins não pode rodar todos juntos."""
    trava = threading.Lock()
    ativos = pico = 0

    def scrypt_lento(*_, dklen, **__):
        nonlocal ativos, pico
        with trava:
            ativos += 1
            pico = max(pico, ativos)
        time.sleep(0.02)
        with trava:
            ativos -= 1
        return bytes(dklen)

    monkeypatch.setattr(senha.hashlib, "scrypt", scrypt_lento)
    rajada = [threading.Thread(target=conferir, args=("x", HASH_FIXO)) for _ in range(20)]
    for thread in rajada:
        thread.start()
    for thread in rajada:
        thread.join()

    assert 1 < pico <= senha.SIMULTANEOS
