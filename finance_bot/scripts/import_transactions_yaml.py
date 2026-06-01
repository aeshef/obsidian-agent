#!/usr/bin/env python3
"""
Импорт/восстановление транзакций из YAML (append, дедуп по дате+сумме+описанию+счёту).

  python scripts/import_transactions_yaml.py --file config/recover_session_20260531.yaml
  python scripts/import_transactions_yaml.py --file config/recover_session_20260531.yaml --db /path/finance.db
"""
from __future__ import annotations

import argparse
import calendar
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.finance_db_paths import mirror_canonical_to_vault_replica, resolve_canonical_write_db  # noqa: E402


def _occurred(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> str:
    return datetime(year, month, day, hour, minute, 0).strftime("%Y-%m-%d %H:%M:%S")


def _ensure_account(cur: sqlite3.Cursor, user_id: int, name: str) -> int:
    row = cur.execute(
        "SELECT id FROM accounts WHERE user_id=? AND name=?",
        (user_id, name),
    ).fetchone()
    if row:
        return int(row[0])
    cur.execute(
        """INSERT INTO accounts (user_id, name, type, currency, is_external_balance, external_balance, created_at)
           VALUES (?, ?, 'card', 'RUB', 0, 0, datetime('now'))""",
        (user_id, name),
    )
    return int(cur.lastrowid)


def _exists(
    cur: sqlite3.Cursor,
    user_id: int,
    account_id: int,
    txn_type: str,
    amount: float,
    occurred: str,
    description: str,
) -> bool:
    row = cur.execute(
        """SELECT 1 FROM transactions
           WHERE user_id=? AND account_id=? AND type=? AND amount=? AND occurred_at=? AND description=?
           LIMIT 1""",
        (user_id, account_id, txn_type, amount, occurred, description),
    ).fetchone()
    return row is not None


def _insert_expense(
    cur: sqlite3.Cursor,
    user_id: int,
    account_id: int,
    amount: float,
    category: str,
    description: str,
    occurred: str,
) -> bool:
    if _exists(cur, user_id, account_id, "expense", amount, occurred, description):
        return False
    cur.execute(
        """INSERT INTO transactions
           (user_id, account_id, type, amount, currency, category, description, occurred_at, created_at)
           VALUES (?, ?, 'expense', ?, 'RUB', ?, ?, ?, datetime('now'))""",
        (user_id, account_id, amount, category, description, occurred),
    )
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path, required=True)
    ap.add_argument("--vault", type=Path, default=None)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--user-id", type=int, default=1)
    args = ap.parse_args()

    import_path = args.file if args.file.is_absolute() else ROOT / args.file
    data = yaml.safe_load(import_path.read_text(encoding="utf-8"))
    ym = str(data.get("year_month", "")).strip()
    y, m = map(int, ym.split("-")[:2])
    default_account = str(data.get("account_name", "Яндекс Банк"))

    if args.db:
        db_path = args.db
    else:
        if args.vault:
            import os
            os.environ["VAULT_PATH"] = str(args.vault.expanduser().resolve())
        db_path = resolve_canonical_write_db()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    added = 0
    skipped = 0

    for raw in data.get("transactions") or []:
        day = int(raw["day"])
        amount = float(raw["amount"])
        category = str(raw.get("category") or "Прочее")
        description = str(raw.get("description") or "")
        account_name = str(raw.get("account") or default_account)
        occurred = _occurred(y, m, day)
        acc_id = _ensure_account(cur, args.user_id, account_name)
        if _insert_expense(cur, args.user_id, acc_id, amount, category, description, occurred):
            added += 1
            print(f"  + expense {amount} {occurred} {description}")
        else:
            skipped += 1
            print(f"  ~ skip (exists) {amount} {occurred} {description}")

    for raw in data.get("transfers") or []:
        day = int(raw["day"])
        amount = float(raw["amount"])
        from_name = str(raw["from_account"])
        to_name = str(raw["to_account"])
        description = str(raw.get("description") or f"Перевод {from_name} → {to_name}")
        occurred = _occurred(y, m, day)
        from_id = _ensure_account(cur, args.user_id, from_name)
        to_id = _ensure_account(cur, args.user_id, to_name)
        exp_desc = f"Перевод на {to_name}"
        inc_desc = f"Перевод с {from_name}"
        if not _exists(cur, args.user_id, from_id, "expense", amount, occurred, exp_desc):
            cur.execute(
                """INSERT INTO transactions
                   (user_id, account_id, type, amount, currency, category, description, occurred_at, created_at)
                   VALUES (?, ?, 'expense', ?, 'RUB', 'Перевод', ?, ?, datetime('now'))""",
                (args.user_id, from_id, amount, exp_desc, occurred),
            )
            added += 1
            print(f"  + transfer out {amount} {from_name}")
        else:
            skipped += 1
        if not _exists(cur, args.user_id, to_id, "income", amount, occurred, inc_desc):
            cur.execute(
                """INSERT INTO transactions
                   (user_id, account_id, type, amount, currency, category, description, occurred_at, created_at)
                   VALUES (?, ?, 'income', ?, 'RUB', 'Перевод', ?, ?, datetime('now'))""",
                (args.user_id, to_id, amount, inc_desc, occurred),
            )
            added += 1
            print(f"  + transfer in {amount} {to_name}")
        else:
            skipped += 1

    conn.commit()
    mx = cur.execute("SELECT max(id), count(*) FROM transactions").fetchone()
    conn.close()
    mirror_canonical_to_vault_replica(canonical=Path(db_path))
    print(f"✅ {db_path}: добавлено {added}, пропущено {skipped}, max_id={mx[0]}, total={mx[1]}")


if __name__ == "__main__":
    main()
