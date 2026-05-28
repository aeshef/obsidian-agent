#!/usr/bin/env python3
"""Показать последние транзакции и переводы в читаемом виде."""
import os
import sqlite3
import sys
from pathlib import Path

# Локальная БД или с сервера - путь можно передать
db_path = Path(__file__).parent.parent / "finance.db"
if len(sys.argv) > 1:
    db_path = Path(sys.argv[1])

if not db_path.exists():
    print(f"БД не найдена: {db_path}")
    print("Запуск: python scripts/show_recent_txns.py [путь/к/finance.db]")
    sys.exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""
  SELECT t.id, t.type, t.amount, t.currency, t.category, t.description, t.occurred_at, a.name as account_name
  FROM transactions t
  JOIN accounts a ON t.account_id = a.id
  ORDER BY t.occurred_at DESC
  LIMIT 50
""")
rows = cur.fetchall()

print("=== Последние транзакции ===\n")
for r in rows:
    occ = r["occurred_at"][:19] if r["occurred_at"] else ""
    typ = r["type"]
    amt = float(r["amount"])
    curr = r["currency"] or "RUB"
    acc = (r["account_name"] or "")[:24]
    cat = (r["category"] or "-")[:20]
    desc = (r["description"] or "")[:30]
    print(f"{occ}  {typ:8}  {amt:>12,.2f} {curr:3}  {acc:24}  {cat:20}  {desc}")
print()

# Отдельно переводы (категория "Перевод" или тип с двух сторон)
cur.execute("""
  SELECT t.id, t.type, t.amount, t.currency, t.category, t.description, t.occurred_at, a.name as account_name
  FROM transactions t
  JOIN accounts a ON t.account_id = a.id
  WHERE t.category IN ('Перевод', 'Переводы') OR t.description LIKE 'Перевод%'
  ORDER BY t.occurred_at DESC
  LIMIT 20
""")
rows = cur.fetchall()
print("=== Транзакции-переводы (категория/описание «Перевод») ===\n")
for r in rows:
    occ = r["occurred_at"][:19] if r["occurred_at"] else ""
    typ = r["type"]
    amt = float(r["amount"])
    curr = r["currency"] or "RUB"
    acc = (r["account_name"] or "")[:24]
    desc = (r["description"] or "")[:50]
    print(f"{occ}  {typ:8}  {amt:>12,.2f} {curr:3}  {acc:24}  {desc}")
print()

# Балансы по счетам: внешний (если включён) и посчитанный по транзакциям
cur.execute("SELECT id, name, is_external_balance, external_balance FROM accounts ORDER BY name")
accounts = cur.fetchall()
cur.execute("""
  SELECT account_id,
    SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) - SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) as balance
  FROM transactions
  GROUP BY account_id
""")
by_account = {r[0]: float(r[1] or 0) for r in cur.fetchall()}

print("=== Балансы по счетам ===\n")
for a in accounts:
    aid, name, is_ext, ext_bal = a["id"], a["name"], a["is_external_balance"], a["external_balance"]
    computed = by_account.get(aid, 0)
    ext_bal = float(ext_bal) if ext_bal is not None else None
    if is_ext and ext_bal is not None:
        show = f"external_balance = {ext_bal:,.2f} (транзакции не учитываются)"
    else:
        base = (ext_bal or 0) if ext_bal is not None else 0
        total = base + computed
        show = f"({base:,.2f} + сумма транзакций {computed:,.2f}) = {total:,.2f}"
    print(f"  {name}: {show}")
print()

# Возможные дубликаты: одинаковые дата+тип+сумма+счёт+описание
cur.execute("""
  SELECT account_id, type, amount, occurred_at, description, COUNT(*) as cnt
  FROM transactions
  GROUP BY account_id, type, amount, occurred_at, COALESCE(description,'')
  HAVING COUNT(*) > 1
  ORDER BY cnt DESC
""")
dupes = cur.fetchall()
if dupes:
    print("=== Возможные дубликаты транзакций (одинаковые дата, тип, сумма, счёт, описание) ===\n")
    acc_ids = {a["id"]: a["name"] for a in accounts}
    for d in dupes:
        name = acc_ids.get(d["account_id"], str(d["account_id"]))
        occ = (d["occurred_at"] or "")[:19]
        desc = (d["description"] or "")[:40]
        print(f"  {occ}  {d['type']}  {float(d['amount']):,.2f}  {name}  x{d['cnt']}  {desc}")
    print()
else:
    print("=== Дубликатов по (дата, тип, сумма, счёт, описание) не найдено ===\n")

# Детально по одному счёту (опционально): задай имя в FINANCE_DEBUG_ACCOUNT, например:
#   FINANCE_DEBUG_ACCOUNT='Моя карта' python scripts/show_recent_txns.py
_debug_name = (os.environ.get("FINANCE_DEBUG_ACCOUNT") or "").strip()
if _debug_name:
    yb = cur.execute("SELECT id FROM accounts WHERE name = ?", (_debug_name,)).fetchone()
else:
    yb = None
if yb:
    yb_id = yb[0]
    cur.execute("""
      SELECT id, type, amount, occurred_at, category, description
      FROM transactions
      WHERE account_id = ?
      ORDER BY occurred_at DESC
    """, (yb_id,))
    yb_txns = cur.fetchall()
    cur.execute(
      "SELECT SUM(CASE WHEN type='income' THEN amount ELSE 0 END) - SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) FROM transactions WHERE account_id = ?",
      (yb_id,),
    )
    yb_sum = cur.fetchone()[0] or 0
    print(f"=== Все транзакции по счёту «{_debug_name}» ===\n")
    for t in yb_txns:
        print(f"  id={t['id']}  {t['occurred_at'][:19]}  {t['type']:8}  {float(t['amount']):>12,.2f}  {t['category'] or '-'}  {t['description'] or ''}")
    print(f"\n  Итого по транзакциям (income - expense): {float(yb_sum):,.2f}")
    print()

conn.close()
