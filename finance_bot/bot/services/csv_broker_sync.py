"""CSV broker portfolio sync — update external balances from a local/exported file.

Expected columns (header, case-insensitive):
  name, balance
Optional: currency

Rows match finance ``accounts.name``. Only accounts with ``is_external_balance``
are updated (create is not performed — set up accounts once in the bot).
"""
from __future__ import annotations

import csv
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from shared.finance.broker_sync_config import load_broker_sync_yaml
from shared.finance.currency import base_currency

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from finance_bot.bot.models import User

log = logging.getLogger("finance.broker.csv")


def _csv_path_from_config() -> Path:
    cfg = load_broker_sync_yaml()
    block = cfg.get("csv") if isinstance(cfg.get("csv"), dict) else {}
    raw = str((block or {}).get("path") or cfg.get("csv_path") or "").strip()
    if not raw:
        raise ValueError(
            "broker provider 'csv' needs csv.path in broker_sync.yaml "
            "(e.g. csv: { path: ./data/broker_balances.csv })"
        )
    p = Path(raw).expanduser()
    if not p.is_absolute():
        # Relative to finance_bot/config/
        root = Path(__file__).resolve().parents[2] / "config"
        p = (root / p).resolve()
    return p


def _parse_balance(raw: str) -> Decimal:
    s = (raw or "").strip().replace(" ", "").replace(",", ".")
    if not s:
        raise InvalidOperation("empty")
    return Decimal(s)


async def sync_csv_balances(session: "AsyncSession", user: "User") -> str:
    from finance_bot.bot.models import Account

    path = _csv_path_from_config()
    if not path.is_file():
        raise ValueError(f"CSV not found: {path}")

    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        fields = {h.strip().lower(): h for h in reader.fieldnames if h}
        if "name" not in fields or "balance" not in fields:
            raise ValueError("CSV must have columns: name, balance (optional: currency)")
        rows = list(reader)

    updated = 0
    skipped = 0
    lines: list[str] = []
    for row in rows:
        name = (row.get(fields["name"]) or "").strip()
        if not name:
            continue
        try:
            bal = _parse_balance(row.get(fields["balance"]) or "")
        except (InvalidOperation, ValueError):
            skipped += 1
            continue
        ccy_key = fields.get("currency")
        currency = (
            (row.get(ccy_key) or "").strip().upper()
            if ccy_key
            else base_currency()
        ) or base_currency()

        result = await session.execute(
            select(Account).where(Account.user_id == user.id, Account.name == name)
        )
        acc = result.scalar_one_or_none()
        if acc is None:
            skipped += 1
            lines.append(f"skip (no account): {name}")
            continue
        if not acc.is_external_balance:
            skipped += 1
            lines.append(f"skip (not external): {name}")
            continue
        acc.external_balance = bal
        if currency:
            acc.currency = currency
        updated += 1
        lines.append(f"{name}: {bal} {currency}")

    await session.commit()
    header = f"CSV broker sync: updated={updated} skipped={skipped} file={path.name}"
    log.info(header)
    body = "\n".join(lines[:40])
    return f"<pre>\n{header}\n{body}\n</pre>"
