"""Lightweight SQLite schema migrations without Alembic."""
from __future__ import annotations

import logging
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

log = logging.getLogger("finance.schema")


def _accounts_has_column(conn: Connection, column: str) -> bool:
    insp = inspect(conn)
    if not insp.has_table("accounts"):
        return False
    return column in {c["name"] for c in insp.get_columns("accounts")}


def ensure_accounts_external_ref(conn: Connection) -> None:
    if _accounts_has_column(conn, "external_ref"):
        return
    conn.execute(text("ALTER TABLE accounts ADD COLUMN external_ref VARCHAR(64)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_accounts_external_ref ON accounts (external_ref)"))
    log.info("Added accounts.external_ref column")


def ensure_wal_journal_mode(conn: Connection) -> None:
    row = conn.execute(text("PRAGMA journal_mode")).fetchone()
    mode = (row[0] if row else "").lower()
    if mode != "wal":
        conn.execute(text("PRAGMA journal_mode=WAL"))
        log.info("SQLite journal_mode set to WAL (was %s)", mode or "unknown")


def run_schema_migrations(conn: Connection) -> None:
    ensure_wal_journal_mode(conn)
    ensure_accounts_external_ref(conn)
