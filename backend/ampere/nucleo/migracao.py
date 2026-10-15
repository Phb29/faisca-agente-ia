"""Migrações do esquema: os `.sql` de `migracoes/` em ordem alfabética, cada um aplicado uma
única vez, mais as tabelas do checkpointer e do Store do LangGraph."""

from pathlib import Path

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore

from ampere.nucleo.banco import conectar

PASTA_MIGRACOES = Path(__file__).parent / "migracoes"

TABELAS_NOSSAS = (
    "execucoes_de_eval",
    "tickets",
    "aprovacoes_pendentes",
    "fila_de_jobs",
    "mensagens",
    "conversas",
    "reembolsos",
    "pedidos",
    "clientes",
    "migracoes",
)


def migrar(conn_string: str) -> list[str]:
    """Aplica as migrações ainda não registradas e prepara as tabelas do LangGraph.
    Devolve os nomes dos arquivos aplicados nesta chamada."""
    aplicadas: list[str] = []
    with conectar(conn_string) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS migracoes "
            "(nome text PRIMARY KEY, aplicada_em timestamptz NOT NULL DEFAULT now())"
        )
        conn.commit()
        registradas = {r["nome"] for r in conn.execute("SELECT nome FROM migracoes").fetchall()}
        for arquivo in sorted(PASTA_MIGRACOES.glob("*.sql")):
            if arquivo.name in registradas:
                continue
            with conn.transaction():
                conn.execute(arquivo.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO migracoes (nome) VALUES (%s)", (arquivo.name,))
            aplicadas.append(arquivo.name)

    # O checkpointer e o Store criam as próprias tabelas, com DDL fora de transação.
    with conectar(conn_string, autocommit=True) as conn:
        PostgresSaver(conn).setup()
        PostgresStore(conn).setup()
    return aplicadas


def apagar_tudo(conn_string: str) -> None:
    """Só para testes: derruba as tabelas nossas e as do LangGraph."""
    with conectar(conn_string, autocommit=True) as conn:
        for tabela in TABELAS_NOSSAS:
            conn.execute(f"DROP TABLE IF EXISTS {tabela} CASCADE")
        do_langgraph = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() "
            "AND (tablename LIKE 'checkpoint%%' OR tablename LIKE 'store%%' "
            "OR tablename LIKE 'vector%%')"
        ).fetchall()
        for linha in do_langgraph:
            conn.execute(f'DROP TABLE IF EXISTS "{linha["tablename"]}" CASCADE')
