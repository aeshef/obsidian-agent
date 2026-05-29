#!/usr/bin/env python3
"""
Одноразовый скрипт: вносит в БД запись расхода «долг» так же, как после изменений в прод.
Пример: 5000 RUB со счёта «Т-Банк» (если есть), категория Долги, описание-заглушка для теста БД.
Запуск из корня finance_bot: python scripts/insert_debt_expense_example.py [путь/к/finance.db]
"""
import os
import sys
from pathlib import Path
from datetime import datetime

import sqlite3


def main():
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
    else:
        url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./finance.db")
        if url.startswith("sqlite:///"):
            db_path = Path(url.replace("sqlite:///", ""))
        elif url.startswith("sqlite+aiosqlite:///"):
            db_path = Path(url.replace("sqlite+aiosqlite:///", ""))
        else:
            db_path = Path("finance.db")
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
        "SELECT id, name FROM accounts WHERE user_id = ? AND (name = ? OR name = ?)",
        (user_id, "Т-Банк", "Т-банк"),
    )
    row = cur.fetchone()
    if not row:
        cur.execute(
            "SELECT id, name FROM accounts WHERE user_id = ? AND is_external_balance = 0 ORDER BY id LIMIT 5",
            (user_id,),
        )
        rows = cur.fetchall()
        print("❌ Счёт «Т-Банк» не найден. Доступные счета:", [r[1] for r in rows])
        conn.close()
        sys.exit(1)
    account_id, account_name = row[0], row[1]

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        """INSERT INTO transactions (user_id, account_id, type, amount, currency, category, description, occurred_at, created_at)
           VALUES (?, ?, 'expense', 5000, 'RUB', 'Долги', 'Долг для Пример Контрагент (замени)', ?, ?)""",
        (user_id, account_id, now, now),
    )
    conn.commit()
    print(f"✅ Добавлена запись: расход 5000 RUB с «{account_name}», категория Долги (описание в коде — заглушка).")
    print(f"   (user_id={user_id}, account_id={account_id})")
    conn.close()


if __name__ == "__main__":
    main()
