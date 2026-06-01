#!/usr/bin/env python3
"""
Разовый импорт истории бейджа из YAML (без хардкода в коде).

  python scripts/import_badge_history.py --file config/badge_import_may_2026.yaml
  python scripts/import_badge_history.py --file config/badge_import_may_2026.yaml --db /path/finance.db
  python scripts/import_badge_history.py --clear --file config/badge_import_may_2026.yaml

После успешного импорта на сервер и локаль файл импорта можно удалить.
Дальше — только новые траты через бота (🍽 Бейдж).
"""

from __future__ import annotations

import argparse
import calendar
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.config_loader import get_badge_config  # noqa: E402
from bot.finance_db_paths import mirror_canonical_to_vault_replica, resolve_canonical_write_db  # noqa: E402


def load_import_file(path: Path) -> tuple[str, list[dict]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Ожидался объект YAML в {path}")
    ym = str(data.get("year_month", "")).strip()
    if len(ym) < 7:
        raise ValueError("В файле нужно поле year_month: YYYY-MM")
    txns = data.get("transactions") or []
    if not isinstance(txns, list) or not txns:
        raise ValueError("В файле нужен непустой список transactions")
    return ym, txns


def main() -> None:
    parser = argparse.ArgumentParser(description="Разовый импорт трат бейджа из YAML")
    parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="YAML с year_month и transactions (day, amount, description)",
    )
    parser.add_argument("--vault", type=Path, default=None)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--account-name", default=None, help="Имя счёта бейджа (override badge.yaml)")
    parser.add_argument("--category", default=None, help="Категория (override badge.yaml)")
    parser.add_argument("--clear", action="store_true", help="Удалить траты бейджа за month из файла")
    parser.add_argument(
        "--append",
        action="store_true",
        help="Только добавить строки (не удалять существующие; пропуск дубликатов по дате+сумме+описанию)",
    )
    args = parser.parse_args()

    import_path = args.file if args.file.is_absolute() else ROOT / args.file
    if not import_path.exists():
        print(f"❌ Файл не найден: {import_path}")
        sys.exit(1)

    year_month, raw_txns = load_import_file(import_path)
    y, m = map(int, year_month.split("-")[:2])
    _, last_day = calendar.monthrange(y, m)

    cfg = get_badge_config()
    account_name = args.account_name or cfg.get("account_name", "Yandex Badge")
    category = args.category or cfg.get("category", "Еда/Бейдж")

    if args.db:
        db_path = Path(args.db)
    else:
        if args.vault:
            import os
            os.environ["VAULT_PATH"] = str(args.vault.expanduser().resolve())
        db_path = resolve_canonical_write_db()

    if not db_path.exists():
        print(f"❌ БД не найдена: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    acc = cur.execute(
        "SELECT id FROM accounts WHERE user_id=? AND name=?",
        (args.user_id, account_name),
    ).fetchone()
    if not acc:
        cur.execute(
            """INSERT INTO accounts (user_id, name, type, currency, is_external_balance, external_balance, created_at)
               VALUES (?, ?, 'badge', 'RUB', 0, 0, datetime('now'))""",
            (args.user_id, account_name),
        )
        acc_id = cur.lastrowid
        print(f"✅ Создан счёт {account_name} id={acc_id}")
    else:
        acc_id = acc[0]

    start = f"{y:04d}-{m:02d}-01"
    end = f"{y + 1:04d}-01-01" if m == 12 else f"{y:04d}-{m + 1:02d}-01"

    if args.clear:
        cur.execute(
            """DELETE FROM transactions
               WHERE user_id=? AND account_id=? AND category=?
                 AND occurred_at >= ? AND occurred_at < ?""",
            (args.user_id, acc_id, category, start, end),
        )
        conn.commit()
        print(f"🗑 Удалено за {year_month}: {cur.rowcount} строк")
        conn.close()
        return

    cleared = 0
    if not args.append:
        cur.execute(
            """DELETE FROM transactions
               WHERE user_id=? AND account_id=? AND category=?
                 AND occurred_at >= ? AND occurred_at < ?""",
            (args.user_id, acc_id, category, start, end),
        )
        cleared = cur.rowcount

    inserted = 0
    skipped = 0
    total = 0
    for row in raw_txns:
        day = int(row["day"])
        amount = int(row["amount"])
        desc = str(row.get("description") or "").strip() or None
        if day < 1 or day > last_day or amount <= 0:
            continue
        d = date(y, m, day)
        hour = int(row.get("hour", 12))
        minute = int(row.get("minute", 0))
        occ = datetime(d.year, d.month, d.day, hour, minute, 0).isoformat(sep=" ")
        if args.append:
            dup = cur.execute(
                """SELECT 1 FROM transactions
                   WHERE user_id=? AND account_id=? AND category=?
                     AND amount=? AND description IS ? AND occurred_at=?""",
                (args.user_id, acc_id, category, amount, desc, occ),
            ).fetchone()
            if dup:
                skipped += 1
                continue
        cur.execute(
            """INSERT INTO transactions
               (user_id, account_id, type, amount, currency, category, description, occurred_at, created_at)
               VALUES (?, ?, 'expense', ?, 'RUB', ?, ?, ?, datetime('now'))""",
            (args.user_id, acc_id, amount, category, desc, occ),
        )
        inserted += 1
        total += amount

    conn.commit()
    conn.close()
    mirror_canonical_to_vault_replica(canonical=Path(db_path))
    mode = "append" if args.append else "replace"
    print(f"✅ Импорт ({mode}) {import_path.name} → {db_path}")
    if not args.append:
        print(f"   Период: {year_month}, заменено старых строк: {cleared}")
    if skipped:
        print(f"   Пропущено дубликатов: {skipped}")
    print(f"   Добавлено: {inserted} операций на {_fmt(total)} ₽")


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


if __name__ == "__main__":
    main()
