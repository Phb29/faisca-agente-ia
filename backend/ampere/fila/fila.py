"""A fila de jobs no Postgres: enfileirar, reservar com SKIP LOCKED e concluir.

Enfileirar também avisa os workers com `NOTIFY fila_de_jobs`, dentro da mesma transação: o
aviso só sai se o job foi gravado, e o worker acorda na hora em vez de esperar a próxima
volta do polling. Os jobs do chat pertencem a uma Conversa e publicam no canal dela; um job
sem Conversa (a amostra ao vivo dos evals) traz o próprio canal. A fila não sabe o que cada
tipo de job faz: quem sabe é o executor que a raiz de composição liga a cada tipo.
"""

from dataclasses import dataclass
from typing import Literal

import psycopg
from psycopg.types.json import Jsonb

from ampere.conversas.conversas import atualizar_status, gravar_mensagem, titulo_a_partir_de
from ampere.fila.eventos import canal as canal_da_conversa

CANAL_DA_FILA = "fila_de_jobs"
TipoDeJob = Literal["mensagem", "retomada", "eval"]
# Um job em processamento há mais tempo que isso é de um worker que morreu: ele deixa de
# segurar a Conversa (o job preso em si continua sem recuperação).
MINUTOS_ATE_LIBERAR_A_CONVERSA = 10


@dataclass(frozen=True)
class Job:
    """`canal` é onde o worker publica os eventos do job: o da Conversa, para o chat, ou um
    próprio, para jobs sem Conversa."""

    id: int
    tipo: TipoDeJob
    conversa_id: str | None
    message_id: str | None
    payload: dict
    canal: str = ""


def _travar_conversa(conn: psycopg.Connection, conversa_id: str) -> None:
    """Trava a linha da Conversa até o fim da transação. Sem isso, dois enfileiramentos da
    mesma Conversa em conexões concorrentes podem confirmar fora da ordem em que pediram o
    id (ex.: o id 7 commita antes do 6), e a reserva por `anterior.id < f.id` deixa passar
    dois jobs da mesma Conversa juntos. Travando a Conversa primeiro, quem pede o id depois
    também commita depois."""
    conn.execute("SELECT 1 FROM conversas WHERE id = %s FOR UPDATE", (conversa_id,))


def enfileirar_mensagem(
    conn: psycopg.Connection, conversa_id: str, message_id: str, conteudo: str, cliente_id: str
) -> bool:
    """Grava a mensagem do Cliente e o job numa transação só. Devolve False quando o
    `message_id` já existia: o reenvio é ignorado sem erro (idempotência)."""
    with conn.transaction():
        _travar_conversa(conn, conversa_id)
        if gravar_mensagem(conn, conversa_id, "cliente", conteudo, message_id) is None:
            return False
        conn.execute(
            "INSERT INTO fila_de_jobs (tipo, conversa_id, message_id, payload) "
            "VALUES ('mensagem', %s, %s, %s)",
            (conversa_id, message_id, Jsonb({"conteudo": conteudo, "cliente_id": cliente_id})),
        )
        atualizar_status(conn, conversa_id, "aberta", titulo_se_vazio=titulo_a_partir_de(conteudo))
        _avisar_workers(conn)
    return True


def enfileirar_retomada(
    conn: psycopg.Connection,
    conversa_id: str,
    aprovacao_id: str,
    aprovado: bool,
    motivo: str | None,
    cliente_id: str,
) -> int:
    """Job que retoma a Conversa congelada com a decisão do Atendente."""
    payload = {
        "aprovacao_id": str(aprovacao_id),
        "aprovado": aprovado,
        "motivo": motivo,
        "cliente_id": cliente_id,
    }
    with conn.transaction():
        _travar_conversa(conn, conversa_id)
        linha = conn.execute(
            "INSERT INTO fila_de_jobs (tipo, conversa_id, payload) "
            "VALUES ('retomada', %s, %s) RETURNING id",
            (conversa_id, Jsonb(payload)),
        ).fetchone()
        _avisar_workers(conn)
    return linha["id"]


def enfileirar_sem_conversa(
    conn: psycopg.Connection, *, tipo: TipoDeJob, canal: str, payload: dict
) -> int:
    """Job que não pertence a uma Conversa e publica no `canal` dado. O banco só aceita job
    sem Conversa do tipo `eval` (ver a migração 0004). Dentro de uma transação de quem
    chama, o job e o aviso só valem se ela for confirmada."""
    with conn.transaction():
        linha = conn.execute(
            "INSERT INTO fila_de_jobs (tipo, canal, payload) VALUES (%s, %s, %s) RETURNING id",
            (tipo, canal, Jsonb(payload)),
        ).fetchone()
        _avisar_workers(conn)
    return linha["id"]


_RESERVAR = """
UPDATE fila_de_jobs SET status = 'processando', iniciado_em = now()
WHERE id = (
    SELECT f.id FROM fila_de_jobs AS f
    WHERE f.status = 'pendente'
      AND NOT EXISTS (
          SELECT 1 FROM fila_de_jobs AS anterior
          WHERE anterior.conversa_id = f.conversa_id AND anterior.id < f.id
            AND (anterior.status = 'pendente'
                 OR (anterior.status = 'processando'
                     AND anterior.iniciado_em > now() - make_interval(mins => %s))))
    ORDER BY f.id FOR UPDATE SKIP LOCKED LIMIT 1
)
RETURNING id, tipo, conversa_id::text, message_id, payload, canal
"""


def pegar_proximo_job(conn: psycopg.Connection) -> Job | None:
    """Reserva o job pendente mais antigo com `FOR UPDATE SKIP LOCKED`: dois workers nunca
    pegam o mesmo e nenhum espera o outro. Um job só é reservado quando nenhum job mais
    antigo da mesma Conversa está pendente ou em processamento, para duas mensagens da mesma
    Conversa nunca rodarem juntas sobre o mesmo thread do LangGraph. Isso também fecha a
    corrida entre dois workers: enquanto o primeiro não confirma a reserva do job mais
    antigo, o segundo ainda o vê como pendente e pula o seguinte. `anterior.id < f.id`
    só vale como ordem porque `_travar_conversa` garante que os ids de uma Conversa são
    confirmados na mesma ordem em que foram pedidos."""
    with conn.transaction():
        linha = conn.execute(_RESERVAR, (MINUTOS_ATE_LIBERAR_A_CONVERSA,)).fetchone()
    if linha is None:
        return None
    return Job(**{**linha, "canal": linha["canal"] or canal_da_conversa(linha["conversa_id"])})


def concluir_job(conn: psycopg.Connection, job_id: int, erro: str | None = None) -> None:
    conn.execute(
        "UPDATE fila_de_jobs SET status = %s, concluido_em = now(), erro = %s WHERE id = %s",
        ("erro" if erro else "concluido", erro, job_id),
    )


def _avisar_workers(conn: psycopg.Connection) -> None:
    conn.execute(f"NOTIFY {CANAL_DA_FILA}")
