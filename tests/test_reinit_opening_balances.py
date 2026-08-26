"""Tests for opening-balance reinit (transactions preserved)."""
from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from bot.services.reinit_opening_balances import (
    AccountTarget,
    apply_reinit_plan,
    build_reinit_plan,
    count_transactions,
    current_balance,
    required_external,
    txn_net_for_account,
    verify_plan_against_db,
)


def _schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name VARCHAR(64) NOT NULL,
            type VARCHAR(24) NOT NULL,
            currency VARCHAR(8) NOT NULL,
            is_external_balance BOOLEAN NOT NULL,
            external_balance NUMERIC(18,2),
            created_at DATETIME,
            external_ref VARCHAR(64)
        );
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            type VARCHAR(8) NOT NULL,
            amount NUMERIC(18,2) NOT NULL,
            currency VARCHAR(8) NOT NULL,
            category VARCHAR(64),
            description VARCHAR(256),
            occurred_at DATETIME,
            created_at DATETIME
        );
        """
    )


def _seed_card(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        """
        INSERT INTO accounts (user_id, name, type, currency, is_external_balance, external_balance)
        VALUES (1, 'Demo Bank', 'card', 'RUB', 0, 1000)
        """
    )
    aid = cur.lastrowid
    conn.execute(
        """
        INSERT INTO transactions (user_id, account_id, type, amount, currency, occurred_at, created_at)
        VALUES
          (1, ?, 'income', 500, 'RUB', '2026-01-01', '2026-01-01'),
          (1, ?, 'expense', 200, 'RUB', '2026-01-02', '2026-01-02')
        """,
        (aid, aid),
    )
    conn.commit()
    return int(aid)


def test_required_external_ledger_math():
    # current = 1000 + 500 - 200 = 1300; target 2000 → ext = 2000 - 300 = 1700
    assert required_external(
        target=Decimal("2000"),
        is_external_balance=False,
        txn_net=Decimal("300"),
    ) == Decimal("1700")
    assert required_external(
        target=Decimal("5000"),
        is_external_balance=True,
        txn_net=Decimal("999"),
    ) == Decimal("5000")


def test_build_and_apply_preserves_transactions(tmp_path: Path):
    db = tmp_path / "finance.db"
    conn = sqlite3.connect(db)
    _schema(conn)
    aid = _seed_card(conn)
    assert txn_net_for_account(conn, aid) == Decimal("300")
    assert current_balance(
        is_external_balance=False,
        external_balance=Decimal("1000"),
        txn_net=Decimal("300"),
    ) == Decimal("1300")

    before = count_transactions(conn)
    plan = build_reinit_plan(conn, [AccountTarget("Demo Bank", Decimal("10000"))])
    assert len(plan) == 1
    assert plan[0].old_current == Decimal("1300")
    assert plan[0].new_external == Decimal("9700")  # 10000 - 300

    apply_reinit_plan(conn, plan, dry_run=False)
    assert count_transactions(conn) == before
    verified = verify_plan_against_db(conn, plan)
    assert verified["Demo Bank"] == Decimal("10000")
    conn.close()


def test_missing_account_raises(tmp_path: Path):
    db = tmp_path / "finance.db"
    conn = sqlite3.connect(db)
    _schema(conn)
    conn.commit()
    try:
        build_reinit_plan(conn, [AccountTarget("Нет такого", Decimal("1"))])
        assert False, "expected KeyError"
    except KeyError as e:
        assert "Нет такого" in str(e)
    finally:
        conn.close()


def test_dry_run_does_not_write(tmp_path: Path):
    db = tmp_path / "finance.db"
    conn = sqlite3.connect(db)
    _schema(conn)
    _seed_card(conn)
    plan = build_reinit_plan(conn, [AccountTarget("Demo Bank", Decimal("9999"))])
    apply_reinit_plan(conn, plan, dry_run=True)
    ext = conn.execute(
        "SELECT external_balance FROM accounts WHERE name='Demo Bank'"
    ).fetchone()[0]
    assert Decimal(str(ext)) == Decimal("1000")
    conn.close()
