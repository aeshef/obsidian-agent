#!/usr/bin/env python3
"""Apply finance_bot/config/initial_accounts.yaml to the local SQLite DB (idempotent)."""
from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

import yaml

_FB_ROOT = Path(__file__).resolve().parents[1]
_REPO = _FB_ROOT.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_FB_ROOT) not in sys.path:
    sys.path.insert(0, str(_FB_ROOT))


def _load_doc(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


async def apply(path: Path, *, dry_run: bool = False) -> int:
    from sqlalchemy import select

    from bot.db import AsyncSessionLocal
    from bot.models import Account, User

    doc = _load_doc(path)
    tid_raw = doc.get("telegram_id")
    if tid_raw is None:
        print("telegram_id missing in initial_accounts.yaml", file=sys.stderr)
        return 1
    try:
        tg_id = int(tid_raw)
    except (TypeError, ValueError):
        print(f"invalid telegram_id: {tid_raw!r}", file=sys.stderr)
        return 1

    accounts = doc.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        print("accounts list empty", file=sys.stderr)
        return 1

    created = updated = 0
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if user is None:
            if dry_run:
                print(f"would create user telegram_id={tg_id}")
            else:
                user = User(telegram_id=tg_id, chat_id=tg_id)
                session.add(user)
                await session.flush()
        elif dry_run:
            print(f"user exists id={user.id}")

        uid = user.id if user else -1
        existing = {}
        if not dry_run and user:
            rows = (await session.execute(select(Account).where(Account.user_id == user.id))).scalars().all()
            existing = {a.name.lower(): a for a in rows}

        for row in accounts:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            bal = Decimal(str(row.get("balance") or 0))
            currency = str(row.get("currency") or "RUB").strip().upper()[:8]
            acc_type = str(row.get("type") or "card").strip().lower()
            if acc_type == "cash":
                acc_type = "wallet"

            if dry_run:
                print(f"  account {name!r}: balance={bal} {currency} type={acc_type}")
                continue

            acc = existing.get(name.lower())
            if acc is None:
                acc = Account(
                    user_id=uid,
                    name=name,
                    type=acc_type,
                    currency=currency,
                    external_balance=bal,
                    is_external_balance=False,
                )
                session.add(acc)
                created += 1
            else:
                acc.external_balance = bal
                acc.currency = currency
                acc.type = acc_type
                updated += 1

        if not dry_run:
            await session.commit()

    verb = "would apply" if dry_run else "applied"
    print(f"{verb}: {len(accounts)} account(s) (created={created}, updated={updated})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--file",
        type=Path,
        default=_FB_ROOT / "config" / "initial_accounts.yaml",
        help="Path to initial_accounts.yaml",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.file.is_file():
        print(f"file not found: {args.file}", file=sys.stderr)
        return 1
    return asyncio.run(apply(args.file, dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
