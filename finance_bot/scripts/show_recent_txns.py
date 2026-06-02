#!/usr/bin/env python3
"""Print recent transactions and transfers in a readable format."""
import os
import sqlite3
import sys
from pathlib import Path

from shared.domain_messages import dmsg

db_path = Path(__file__).parent.parent / "finance.db"
if len(sys.argv) > 1:
    db_path = Path(sys.argv[1])

if not db_path.exists():
    print(dmsg("finance_scripts", "show_txn_db_missing", path=db_path))
    print(dmsg("finance_scripts", "show_txn_usage"))
    sys.exit(1)

_transfer_cat = dmsg("finance", "transfer_category")
_transfer_legacy = dmsg("finance_scripts", "transfer_category_legacy")
_transfer_like = _transfer_cat + "%"

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

print(dmsg("finance_scripts", "show_txn_recent_header") + "\n")
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

cur.execute(
    """
  SELECT t.id, t.type, t.amount, t.currency, t.category, t.description, t.occurred_at, a.name as account_name
  FROM transactions t
  JOIN accounts a ON t.account_id = a.id
  WHERE t.category IN (?, ?) OR t.description LIKE ?
  ORDER BY t.occurred_at DESC
  LIMIT 20
""",
    (_transfer_cat, _transfer_legacy, _transfer_like),
)
rows = cur.fetchall()
print(dmsg("finance_scripts", "show_txn_transfers_header") + "\n")
for r in rows:
    occ = r["occurred_at"][:19] if r["occurred_at"] else ""
    typ = r["type"]
    amt = float(r["amount"])
    curr = r["currency"] or "RUB"
    acc = (r["account_name"] or "")[:24]
    desc = (r["description"] or "")[:50]
    print(f"{occ}  {typ:8}  {amt:>12,.2f} {curr:3}  {acc:24}  {desc}")
print()

cur.execute("SELECT id, name, is_external_balance, external_balance FROM accounts ORDER BY name")
accounts = cur.fetchall()
cur.execute("""
  SELECT account_id,
    SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) - SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) as balance
  FROM transactions
  GROUP BY account_id
""")
by_account = {r[0]: float(r[1] or 0) for r in cur.fetchall()}

print(dmsg("finance_scripts", "show_txn_balances_header") + "\n")
for a in accounts:
    aid, name, is_ext, ext_bal = a["id"], a["name"], a["is_external_balance"], a["external_balance"]
    computed = by_account.get(aid, 0)
    ext_bal = float(ext_bal) if ext_bal is not None else None
    if is_ext and ext_bal is not None:
        show = dmsg("finance_scripts", "show_txn_balance_external", balance=ext_bal)
    else:
        base = (ext_bal or 0) if ext_bal is not None else 0
        total = base + computed
        show = dmsg(
            "finance_scripts",
            "show_txn_balance_computed",
            base=base,
            computed=computed,
            total=total,
        )
    print(f"  {name}: {show}")
print()

cur.execute("""
  SELECT account_id, type, amount, occurred_at, description, COUNT(*) as cnt
  FROM transactions
  GROUP BY account_id, type, amount, occurred_at, COALESCE(description,'')
  HAVING COUNT(*) > 1
  ORDER BY cnt DESC
""")
dupes = cur.fetchall()
if dupes:
    print(dmsg("finance_scripts", "show_txn_dupes_header") + "\n")
    acc_ids = {a["id"]: a["name"] for a in accounts}
    for d in dupes:
        name = acc_ids.get(d["account_id"], str(d["account_id"]))
        occ = (d["occurred_at"] or "")[:19]
        desc = (d["description"] or "")[:40]
        print(f"  {occ}  {d['type']}  {float(d['amount']):,.2f}  {name}  x{d['cnt']}  {desc}")
    print()
else:
    print(dmsg("finance_scripts", "show_txn_no_dupes") + "\n")

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
    print(dmsg("finance_scripts", "show_txn_account_header", name=_debug_name) + "\n")
    for t in yb_txns:
        print(
            f"  id={t['id']}  {t['occurred_at'][:19]}  {t['type']:8}  {float(t['amount']):>12,.2f}  {t['category'] or '-'}  {t['description'] or ''}"
        )
    print("\n" + dmsg("finance_scripts", "show_txn_account_total", total=float(yb_sum)) + "\n")

conn.close()
