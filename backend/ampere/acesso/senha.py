"""Hash de senha com scrypt, da biblioteca padrão.

O formato é `scrypt:N:r:p:<sal>:<hash>`, com sal e hash em base64url sem `=` no fim. Não tem
`$` de propósito: num `.env` ou numa variável do Railway, `$` vira interpolação e estraga o
hash sem aviso. Os parâmetros vão junto, então dá para subir o custo no futuro sem invalidar
os hashes antigos.
"""

import base64
import hashlib
import hmac
import secrets

N = 2**15
R = 8
P = 1
TAMANHO = 32
MEMORIA_MAXIMA = 64 * 1024 * 1024  # o scrypt com N=2**15 e r=8 usa 32 MiB

# Hash de uma senha aleatória que ninguém guardou, com o custo padrão. Quando o e-mail não
# bate, o login confere a senha contra ele, para gastar o mesmo tempo de quando o e-mail bate.
HASH_FIXO = "scrypt:32768:8:1:B22zhq1lHmAmaYyEwRj8oA:JZLVjTo3YL21Z7Hg2bYng86caU_-jSPd321nsN4KCl0"


def gerar_hash(senha: str) -> str:
    sal = secrets.token_bytes(16)
    derivado = _scrypt(senha, sal, N, R, P, TAMANHO)
    return f"scrypt:{N}:{R}:{P}:{_codificar(sal)}:{_codificar(derivado)}"


def conferir(senha: str, hash_: str) -> bool:
    """Compara em tempo constante. Hash malformado devolve False, nunca uma exceção."""
    try:
        nome, n, r, p, sal, esperado = hash_.split(":")
        if nome != "scrypt":
            return False
        esperado_em_bytes = _decodificar(esperado)
        obtido = _scrypt(senha, _decodificar(sal), int(n), int(r), int(p), len(esperado_em_bytes))
    except (ValueError, TypeError, OverflowError):
        return False
    return hmac.compare_digest(obtido, esperado_em_bytes)


def _scrypt(senha: str, sal: bytes, n: int, r: int, p: int, tamanho: int) -> bytes:
    return hashlib.scrypt(
        senha.encode(), salt=sal, n=n, r=r, p=p, maxmem=MEMORIA_MAXIMA, dklen=tamanho
    )


def _codificar(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def _decodificar(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))
