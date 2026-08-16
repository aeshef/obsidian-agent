"""Recompute account.external_balance so current balance matches real-life targets.

Transactions are never modified. For ledger accounts:
  current = external_balance + Σ(income) − Σ(expense)
  → new_external = target − txn_net

For is_external_balance accounts (broker/debt):
  current = external_balance
  → new_external = target
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(frozen=True)
class AccountTarget:
    name: str
    target: Decimal


@dataclass(frozen=True)
class ReinitPlanRow:
    account_id: int
    name: str
    is_external_balance: bool
    old_external: Decimal
    txn_net: Decimal
    old_current: Decimal
    target: Decimal
    new_external: Decimal

    @property
    def delta_external(self) -> Decimal:
        return self.new_external - self.old_external


def _d(val) -> Decimal:
    if val is None:
        return Decimal("0")
    return Decimal(str(val)).quantize(Decimal("0.01"))


def txn_net_for_account(conn: sqlite3.Connection, account_id: int) -> Decimal:
    """Same sign convention as dashboard acc_balance / get_balance."""
    row = conn.execute(
        """
        SELECT COALESCE(
            SUM(CASE WHEN type = 'income' THEN amount ELSE -amount END),
            0
        )
        FROM transactions
        WHERE account_id = ?
        """,
        (account_id,),
    ).fetchone()
    return _d(row[0] if row else 0)


def current_balance(
    *,
    is_external_balance: bool,
    external_balance: Decimal,
    txn_net: Decimal,
) -> Decimal:
    if is_external_balance:
        return external_balance
    return external_balance + txn_net


def required_external(
    *,
    target: Decimal,
    is_external_balance: bool,
    txn_net: Decimal,
) -> Decimal:
    if is_external_balance:
        return target
    return target - txn_net


def build_reinit_plan(
    conn: sqlite3.Connection,
    targets: Iterable[AccountTarget],
) -> list[ReinitPlanRow]:
    """Resolve names → plan rows. Raises KeyError if an account name is missing."""
    rows: list[ReinitPlanRow] = []
    for t in targets:
        acc = conn.execute(
            """
            SELECT id, name, is_external_balance, external_balance
            FROM accounts
            WHERE name = ?
            """,
            (t.name,),
        ).fetchone()
        if acc is None:
            raise KeyError(f"account not found: {t.name!r}")
        aid = int(acc[0])
        is_ext = bool(acc[2])
        old_ext = _d(acc[3])
        net = txn_net_for_account(conn, aid) if not is_ext else Decimal("0")
        old_cur = current_balance(
            is_external_balance=is_ext, external_balance=old_ext, txn_net=net
        )
        new_ext = required_external(
            target=t.target, is_external_balance=is_ext, txn_net=net
        )
        rows.append(
            ReinitPlanRow(
                account_id=aid,
                name=str(acc[1]),
                is_external_balance=is_ext,
                old_external=old_ext,
                txn_net=net,
                old_current=old_cur,
                target=t.target,
                new_external=new_ext,
            )
        )
    return rows


def apply_reinit_plan(
    conn: sqlite3.Connection,
    plan: Iterable[ReinitPlanRow],
    *,
    dry_run: bool = True,
) -> list[ReinitPlanRow]:
    plan_list = list(plan)
    if dry_run:
        return plan_list
    for row in plan_list:
        conn.execute(
            "UPDATE accounts SET external_balance = ? WHERE id = ?",
            (str(row.new_external), row.account_id),
        )
    conn.commit()
    return plan_list


def verify_plan_against_db(
    conn: sqlite3.Connection, plan: Iterable[ReinitPlanRow]
) -> Mapping[str, Decimal]:
    """After apply: recompute current balances; must equal targets."""
    out: dict[str, Decimal] = {}
    for row in plan:
        acc = conn.execute(
            "SELECT is_external_balance, external_balance FROM accounts WHERE id = ?",
            (row.account_id,),
        ).fetchone()
        assert acc is not None
        is_ext = bool(acc[0])
        ext = _d(acc[1])
        net = txn_net_for_account(conn, row.account_id) if not is_ext else Decimal("0")
        out[row.name] = current_balance(
            is_external_balance=is_ext, external_balance=ext, txn_net=net
        )
    return out


def count_transactions(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])


def default_targets_2026_08_09() -> list[AccountTarget]:
    """Real-life balances provided by user (RUB)."""
    return [
        AccountTarget("Яндекс Банк", Decimal("213783")),
        AccountTarget("Альфа-Банк", Decimal("53")),
        AccountTarget("Т-Банк", Decimal("0.66")),
        AccountTarget("Ozon Банк", Decimal("10")),
        AccountTarget("Вайлдберис Банк", Decimal("-400")),
        AccountTarget("Jusan Bank", Decimal("5749")),
        AccountTarget("Кошелек", Decimal("6500")),
    ]


def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn
