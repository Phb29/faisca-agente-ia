"""Acesso às tabelas: Conversas, mensagens, fila de jobs, Aprovações Pendentes, Tickets e
Clientes. Funções pequenas que recebem a conexão e não abrem transação por conta própria
(exceto `pegar_proximo_job`, que precisa de uma)."""

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


@dataclass
class Job:
    id: int
    tipo: str
    conversa_id: str
    message_id: str | None
    payload: dict


def _texto(linha: dict[str, Any] | None) -> dict[str, Any] | None:
    """Converte uuids em str para o resto do sistema não depender do tipo do psycopg."""
    if linha is None:
        return None
    return {k: (str(v) if k.endswith("id") and v is not None else v) for k, v in linha.items()}


# --- Conversas e mensagens ---------------------------------------------------------------


def criar_conversa(conn: psycopg.Connection, cliente_id: str, titulo: str | None = None) -> str:
    linha = conn.execute(
        "INSERT INTO conversas (cliente_id, titulo) VALUES (%s, %s) RETURNING id",
        (cliente_id, titulo),
    ).fetchone()
    return str(linha["id"])


def listar_conversas(conn: psycopg.Connection, cliente_id: str) -> list[dict]:
    linhas = conn.execute(
        "SELECT * FROM conversas WHERE cliente_id = %s ORDER BY criada_em DESC", (cliente_id,)
    ).fetchall()
    return [_texto(linha) for linha in linhas]


def obter_conversa(conn: psycopg.Connection, conversa_id: str) -> dict | None:
    return _texto(conn.execute("SELECT * FROM conversas WHERE id = %s", (conversa_id,)).fetchone())


def atualizar_status_conversa(conn: psycopg.Connection, conversa_id: str, status: str) -> None:
    conn.execute(
        "UPDATE conversas SET status = %s, atualizada_em = now() WHERE id = %s",
        (status, conversa_id),
    )


def gravar_mensagem(
    conn: psycopg.Connection,
    conversa_id: str,
    papel: str,
    conteudo: str,
    message_id: str | None = None,
) -> str:
    """Grava e devolve o id. Com `message_id` repetido, não grava e devolve o id existente."""
    linha = conn.execute(
        "INSERT INTO mensagens (conversa_id, papel, conteudo, message_id) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING RETURNING id",
        (conversa_id, papel, conteudo, message_id),
    ).fetchone()
    if linha is None:
        linha = conn.execute(
            "SELECT id FROM mensagens WHERE message_id = %s", (message_id,)
        ).fetchone()
    conn.execute("UPDATE conversas SET atualizada_em = now() WHERE id = %s", (conversa_id,))
    return str(linha["id"])


def listar_mensagens(conn: psycopg.Connection, conversa_id: str) -> list[dict]:
    linhas = conn.execute(
        "SELECT * FROM mensagens WHERE conversa_id = %s ORDER BY criada_em, id", (conversa_id,)
    ).fetchall()
    return [_texto(linha) for linha in linhas]


def ultima_mensagem_do_assistente(conn: psycopg.Connection, conversa_id: str) -> dict | None:
    return _texto(
        conn.execute(
            "SELECT * FROM mensagens WHERE conversa_id = %s AND papel = 'assistente' "
            "ORDER BY criada_em DESC, id DESC LIMIT 1",
            (conversa_id,),
        ).fetchone()
    )


# --- Fila de jobs ------------------------------------------------------------------------


def enfileirar_mensagem(
    conn: psycopg.Connection, conversa_id: str, message_id: str, conteudo: str, cliente_id: str
) -> bool:
    """Grava a mensagem do Cliente e o job numa transação. Devolve False se o `message_id`
    já existia (a mensagem repetida é ignorada, sem erro)."""
    with conn.transaction():
        mensagem = conn.execute(
            "INSERT INTO mensagens (conversa_id, papel, conteudo, message_id) "
            "VALUES (%s, 'cliente', %s, %s) ON CONFLICT (message_id) DO NOTHING RETURNING id",
            (conversa_id, conteudo, message_id),
        ).fetchone()
        if mensagem is None:
            return False
        job = conn.execute(
            "INSERT INTO fila_de_jobs (tipo, conversa_id, message_id, payload) "
            "VALUES ('mensagem', %s, %s, %s) ON CONFLICT (message_id) DO NOTHING RETURNING id",
            (conversa_id, message_id, Jsonb({"conteudo": conteudo, "cliente_id": cliente_id})),
        ).fetchone()
        conn.execute("UPDATE conversas SET atualizada_em = now() WHERE id = %s", (conversa_id,))
        return job is not None


def enfileirar_retomada(
    conn: psycopg.Connection,
    conversa_id: str,
    aprovacao_id: str,
    aprovado: bool,
    motivo: str | None,
    cliente_id: str,
) -> int:
    payload = {
        "aprovacao_id": str(aprovacao_id),
        "aprovado": aprovado,
        "motivo": motivo,
        "cliente_id": cliente_id,
    }
    linha = conn.execute(
        "INSERT INTO fila_de_jobs (tipo, conversa_id, payload) "
        "VALUES ('retomada', %s, %s) RETURNING id",
        (conversa_id, Jsonb(payload)),
    ).fetchone()
    return linha["id"]


def pegar_proximo_job(conn: psycopg.Connection) -> Job | None:
    """Reserva o job pendente mais antigo com `FOR UPDATE SKIP LOCKED`, de modo que dois
    workers nunca pegam o mesmo. Abre e fecha a própria transação."""
    with conn.transaction():
        linha = conn.execute(
            """
            UPDATE fila_de_jobs SET status = 'processando', iniciado_em = now()
            WHERE id = (
                SELECT id FROM fila_de_jobs WHERE status = 'pendente'
                ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
            )
            RETURNING id, tipo, conversa_id, message_id, payload
            """
        ).fetchone()
    if linha is None:
        return None
    return Job(
        id=linha["id"],
        tipo=linha["tipo"],
        conversa_id=str(linha["conversa_id"]),
        message_id=linha["message_id"],
        payload=linha["payload"],
    )


def concluir_job(conn: psycopg.Connection, job_id: int, erro: str | None = None) -> None:
    conn.execute(
        "UPDATE fila_de_jobs SET status = %s, concluido_em = now(), erro = %s WHERE id = %s",
        ("erro" if erro else "concluido", erro, job_id),
    )


# --- Aprovações Pendentes ----------------------------------------------------------------


def criar_aprovacao(
    conn: psycopg.Connection,
    conversa_id: str,
    cliente_id: str,
    pedido_id: str,
    valor: float,
    probabilidade: float,
    resumo: str,
) -> str:
    linha = conn.execute(
        "INSERT INTO aprovacoes_pendentes "
        "(conversa_id, cliente_id, pedido_id, valor, probabilidade, resumo) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (conversa_id, cliente_id, pedido_id, valor, probabilidade, resumo),
    ).fetchone()
    return str(linha["id"])


def listar_aprovacoes_pendentes(conn: psycopg.Connection) -> list[dict]:
    linhas = conn.execute(
        "SELECT * FROM aprovacoes_pendentes WHERE status = 'pendente' ORDER BY criada_em"
    ).fetchall()
    return [_texto(linha) for linha in linhas]


def obter_aprovacao(conn: psycopg.Connection, aprovacao_id: str) -> dict | None:
    return _texto(
        conn.execute("SELECT * FROM aprovacoes_pendentes WHERE id = %s", (aprovacao_id,)).fetchone()
    )


def decidir_aprovacao(
    conn: psycopg.Connection, aprovacao_id: str, aprovada: bool, motivo: str | None = None
) -> dict | None:
    """Marca a decisão só se ainda estiver pendente; devolve a linha atualizada ou None."""
    return _texto(
        conn.execute(
            "UPDATE aprovacoes_pendentes SET status = %s, motivo = %s, decidida_em = now() "
            "WHERE id = %s AND status = 'pendente' RETURNING *",
            ("aprovada" if aprovada else "rejeitada", motivo, aprovacao_id),
        ).fetchone()
    )


# --- Tickets e Clientes ------------------------------------------------------------------


def criar_ticket(
    conn: psycopg.Connection,
    conversa_id: str,
    cliente_id: str,
    resumo: str,
    categoria: str,
    prioridade: str,
) -> str:
    linha = conn.execute(
        "INSERT INTO tickets (conversa_id, cliente_id, resumo, categoria, prioridade) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (conversa_id, cliente_id, resumo, categoria, prioridade),
    ).fetchone()
    return str(linha["id"])


def listar_tickets(conn: psycopg.Connection) -> list[dict]:
    linhas = conn.execute("SELECT * FROM tickets ORDER BY criado_em DESC").fetchall()
    return [_texto(linha) for linha in linhas]


def obter_ticket(conn: psycopg.Connection, ticket_id: str) -> dict | None:
    return _texto(conn.execute("SELECT * FROM tickets WHERE id = %s", (ticket_id,)).fetchone())


def listar_clientes(conn: psycopg.Connection) -> list[dict]:
    linhas = conn.execute("SELECT * FROM clientes ORDER BY nome").fetchall()
    return [_texto(linha) for linha in linhas]
