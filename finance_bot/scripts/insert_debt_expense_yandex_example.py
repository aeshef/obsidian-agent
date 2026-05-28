#!/usr/bin/env python3
"""
Одноразовый скрипт: добавляет расход по категории «Долги» на первый внутренний счёт (по имени).
Пример суммы и описания — заглушки; подставь свои перед запуском в прод.

Запуск:
  python scripts/insert_debt_expense_yandex_example.py [путь/к/finance.db]
"""
import os
import sys
from datetime import datetime
from pathlib import Path

import sqlite3


def resolve_db_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./finance.db")
    if url.startswith("sqlite:///"):
        return Path(url.replace("sqlite:///", ""))
    if url.startswith("sqlite+aiosqlite:///"):
        return Path(url.replace("sqlite+aiosqlite:///", ""))
    return Path("finance.db")


def main() -> None:
    db_path = resolve_db_path()
    if not db_path.exists():
        print(f"❌ БД не найдена: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT id FROM users ORDER BY id LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("❌ В БД нет пользователей")
        conn.close()
        sys.exit(1)
    user_id = row[0]

    cur.execute(
        """SELECT id, name FROM accounts WHERE user_id = ? AND is_external_balance = 0
           ORDER BY name LIMIT 1""",
        (user_id,),
    )
    row = cur.fetchone()
    if not row:
        cur.execute(
            "SELECT id, name FROM accounts WHERE user_id = ? AND is_external_balance = 0 ORDER BY id LIMIT 5",
            (user_id,),
        )
        print("❌ Нет внутренних счетов. Доступные:", [r[1] for r in cur.fetchall()])
        conn.close()
        sys.exit(1)
    account_id, account_name = row[0], row[1]

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    desc = "Долг для Пример Контрагент (замени описание в скрипте)"
    cur.execute(
        """INSERT INTO transactions (user_id, account_id, type, amount, currency, category, description, occurred_at, created_at)
           VALUES (?, ?, 'expense', 10000, 'RUB', 'Долги', ?, ?, ?)""",
        (user_id, account_id, desc, now, now),
    )
    conn.commit()
    print(f"✅ Добавлена запись: расход 10000 RUB с «{account_name}», категория Долги")
    print(f"   (user_id={user_id}, account_id={account_id})")
    conn.close()


if __name__ == "__main__":
    main()
