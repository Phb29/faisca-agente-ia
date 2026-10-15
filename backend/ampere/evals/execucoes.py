"""As execuções dos evals no Postgres: a completa, gravada pelo CLI no fim da rodada, e a
amostra ao vivo, gravada caso a caso pelo worker (ver docs/adr/0009).

As escritas da amostra são guardadas pelo status: `marcar_rodando` só sai de `pendente`,
`anexar_caso` e `concluir` só gravam em `rodando`, e `falhar` só em `pendente` ou
`rodando`. Assim uma amostra liberada como abandonada nunca volta a parecer concluída, e o
executor descobre pela própria escrita, que devolve False, que deve parar.
"""

from typing import Any, Literal

import psycopg
from psycopg.types.json import Jsonb

from ampere.fila.eventos import Evento, publicar

NomeDoEval = Literal["rag", "agente", "juiz"]
EVALS: tuple[str, ...] = ("rag", "agente", "juiz")
# Uma amostra rodando leva menos de um minuto: parada há 5 é de um worker que morreu. Na fila,
# a folga é maior, porque as duas réplicas podem estar ocupadas com o chat da turma.
MINUTOS_RODANDO = 5
MINUTOS_NA_FILA = 10
TEMPO_ESGOTADO = "tempo esgotado"

_SEM_CASOS = (
    "id::text, eval, modo, status, contexto, resumo, erro, criada_em, iniciada_em, concluida_em"
)
_COM_CASOS = _SEM_CASOS + ", casos"

Execucao = dict[str, Any]


def canal_da_execucao(execucao_id: str) -> str:
    """Canal do NOTIFY de uma execução: `avaliacao_` mais o uuid sem hífens."""
    return "avaliacao_" + str(execucao_id).replace("-", "")


def criar_amostra(conn: psycopg.Connection, eval: NomeDoEval) -> str:
    """Nova amostra `pendente`. O índice `uma_amostra_por_vez` recusa com `UniqueViolation`
    se já houver outra pendente ou rodando, de qualquer eval."""
    linha = conn.execute(
        "INSERT INTO execucoes_de_eval (eval, modo) VALUES (%s, 'amostra') RETURNING id::text",
        (eval,),
    ).fetchone()
    return linha["id"]


def salvar_completa(
    conn: psycopg.Connection,
    eval: NomeDoEval,
    *,
    contexto: dict,
    resumo: dict,
    casos: list[dict],
) -> str:
    linha = conn.execute(
        "INSERT INTO execucoes_de_eval "
        "(eval, modo, status, contexto, resumo, casos, iniciada_em, concluida_em) "
        "VALUES (%s, 'completa', 'concluida', %s, %s, %s, now(), now()) RETURNING id::text",
        (eval, Jsonb(contexto), Jsonb(resumo), Jsonb(casos)),
    ).fetchone()
    return linha["id"]


def marcar_rodando(conn: psycopg.Connection, execucao_id: str, contexto: dict) -> bool:
    cursor = conn.execute(
        "UPDATE execucoes_de_eval SET status = 'rodando', iniciada_em = now(), contexto = %s "
        "WHERE id = %s AND status = 'pendente'",
        (Jsonb(contexto), execucao_id),
    )
    return cursor.rowcount == 1


def anexar_caso(conn: psycopg.Connection, execucao_id: str, caso: dict) -> bool:
    cursor = conn.execute(
        "UPDATE execucoes_de_eval SET casos = casos || %s WHERE id = %s AND status = 'rodando'",
        (Jsonb([caso]), execucao_id),
    )
    return cursor.rowcount == 1


def concluir(conn: psycopg.Connection, execucao_id: str, resumo: dict) -> bool:
    cursor = conn.execute(
        "UPDATE execucoes_de_eval SET status = 'concluida', resumo = %s, concluida_em = now() "
        "WHERE id = %s AND status = 'rodando'",
        (Jsonb(resumo), execucao_id),
    )
    return cursor.rowcount == 1


def falhar(conn: psycopg.Connection, execucao_id: str, erro: str) -> bool:
    """Vale também para `pendente`: uma exceção antes de `marcar_rodando` (no sorteio, por
    exemplo) não pode deixar a amostra presa como "na fila"."""
    cursor = conn.execute(
        "UPDATE execucoes_de_eval SET status = 'erro', erro = %s, concluida_em = now() "
        "WHERE id = %s AND status IN ('pendente', 'rodando')",
        (erro, execucao_id),
    )
    return cursor.rowcount == 1


def liberar_abandonadas(conn: psycopg.Connection) -> list[str]:
    """Marca como "tempo esgotado" a amostra rodando há mais de 5 minutos ou na fila há mais
    de 10, e avisa por `error` no canal dela, para uma tela aberta parar de esperar."""
    linhas = conn.execute(
        "UPDATE execucoes_de_eval SET status = 'erro', erro = %s, concluida_em = now() "
        "WHERE modo = 'amostra' AND ("
        "(status = 'rodando' AND iniciada_em < now() - make_interval(mins => %s)) OR "
        "(status = 'pendente' AND criada_em < now() - make_interval(mins => %s))) "
        "RETURNING id::text",
        (TEMPO_ESGOTADO, MINUTOS_RODANDO, MINUTOS_NA_FILA),
    ).fetchall()
    for linha in linhas:
        aviso = Evento(tipo="error", dados={"mensagem": TEMPO_ESGOTADO})
        publicar(conn, canal_da_execucao(linha["id"]), aviso)
    return [linha["id"] for linha in linhas]


def amostra_em_andamento(conn: psycopg.Connection) -> Execucao | None:
    """A amostra pendente ou rodando, de qualquer eval, sem os casos."""
    return conn.execute(
        f"SELECT {_SEM_CASOS} FROM execucoes_de_eval "
        "WHERE modo = 'amostra' AND status IN ('pendente', 'rodando') LIMIT 1"
    ).fetchone()


def listar(conn: psycopg.Connection, eval: NomeDoEval, *, limite: int = 20) -> list[Execucao]:
    """As execuções de um eval, mais novas primeiro, sem os casos."""
    return conn.execute(
        f"SELECT {_SEM_CASOS} FROM execucoes_de_eval WHERE eval = %s "
        "ORDER BY criada_em DESC LIMIT %s",
        (eval, limite),
    ).fetchall()


def obter(conn: psycopg.Connection, execucao_id: str) -> Execucao | None:
    return conn.execute(
        f"SELECT {_COM_CASOS} FROM execucoes_de_eval WHERE id = %s", (execucao_id,)
    ).fetchone()
