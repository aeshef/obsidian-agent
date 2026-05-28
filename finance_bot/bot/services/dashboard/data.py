"""SQLite data loading for dashboard."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from bot.broker_portfolio import is_broker_portfolio_account

def ensure_account_balance_snapshots_table(conn: sqlite3.Connection) -> None:
    """Legacy DB without migration: create snapshots table."""
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_balance_snapshots'"
    )
    if cur.fetchone():
        return
    cur.executescript(
        """
        CREATE TABLE account_balance_snapshots (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            snapshot_date DATE NOT NULL,
            balance NUMERIC(18, 2) NOT NULL,
            UNIQUE (account_id, snapshot_date),
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_abs_account_id ON account_balance_snapshots (account_id);
        """
    )
    conn.commit()
def acc_balance(cur, acc_id: int, is_external: bool, external_bal) -> Decimal:
    """Account balance: broker uses external; cards use base + transactions."""
    if is_external and external_bal is not None:
        return Decimal(str(external_bal))
    cur.execute(
        "SELECT COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE -amount END), 0) FROM transactions WHERE account_id=?",
        (acc_id,),
    )
    txn_sum = Decimal(str(cur.fetchone()[0]))
    base = Decimal(str(external_bal)) if external_bal is not None else Decimal(0)
    return base + txn_sum


def external_rub_non_portfolio_total(
    balances_now: dict[int, Decimal],
    acc_by_id: dict,
) -> float:
    """
    Sum RUB for external-balance accounts that are not Invest API portfolios.
    They lack account_balance_snapshots — carry current balance in daily series.
    """
    s = Decimal(0)
    for aid, bal in balances_now.items():
        a = acc_by_id.get(aid)
        if not a or a.get("currency") not in ("RUB", "RUR"):
            continue
        if not a.get("is_external_balance"):
            continue
        if is_broker_portfolio_account(a.get("type"), True):
            continue
        s += bal
    return float(s)


def load_data(db_path: Path, user_id: int = 1):
    """Load accounts, transactions, and planned_expenses from DB."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        "SELECT id, name, type, currency, is_external_balance, external_balance FROM accounts WHERE user_id=?",
        (user_id,),
    )
    accounts = [dict(row) for row in cur.fetchall()]

    cur.execute(
        """SELECT t.id, t.account_id, t.type, t.amount, t.currency, t.category, t.description, t.occurred_at, a.name as account_name
           FROM transactions t JOIN accounts a ON t.account_id = a.id WHERE t.user_id=?
           ORDER BY t.occurred_at""",
        (user_id,),
    )
    transactions = [dict(row) for row in cur.fetchall()]

    planned = []
    try:
        cur.execute(
            "SELECT name, amount, currency, due_date FROM planned_expenses WHERE user_id=? AND status='active'",
            (user_id,),
        )
        planned = [dict(row) for row in cur.fetchall()]
    except sqlite3.OperationalError:
        pass  # table may not exist in old DB

    conn.close()
    return accounts, transactions, planned


def parse_datetime(dt_str: str) -> Optional[datetime]:
    """Parse date from SQLite (multiple formats)."""
    try:
        if "T" in dt_str or " " in dt_str:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00").replace("+00:00", "")).replace(tzinfo=None)
        else:
            return datetime.strptime(dt_str[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        try:
            return datetime.strptime(dt_str[:10], "%Y-%m-%d")
        except Exception:
            return None
