"""Finance transaction domain logic (NLU write, accounts, missing fields)."""
from __future__ import annotations

import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Optional

from aiogram import types
from sqlalchemy import select

from bot.config_loader import get_nlu_config
from bot.db import AsyncSessionLocal
from bot.models import Account, Transaction, User
from bot.services.categories import load_categories
from shared.domain_messages import dmsg
from shared.finance.entity_names import find_matching_label, labels_equal

log = logging.getLogger("finance.transactions.core")
_TC = ("finance_txn_core",)


def parse_occurred_at(parsed: dict) -> datetime:
    """Parse occurred_at from NLU (YYYY-MM-DD) or use today at noon local."""
    raw = parsed.get("occurred_at")
    if not raw:
        return datetime.now()
    s = (raw if isinstance(raw, str) else str(raw)).strip()[:10]
    if len(s) < 10:
        return datetime.now()
    try:
        y, m, d = int(s[:4]), int(s[5:7]), int(s[8:10])
        return datetime.combine(date(y, m, d), time(12, 0, 0))
    except (ValueError, TypeError):
        return datetime.now()


def looks_like_transaction(text: str) -> bool:
    cfg = get_nlu_config()
    min_len = int(cfg.get("min_text_length", 3) or 3)
    return len((text or "").strip()) >= min_len


def infer_account_type(account_name: str) -> str:
    cfg = get_nlu_config()
    name = (account_name or "").lower()
    for hint in cfg.get("account_type_card_hints") or []:
        if str(hint).lower() in name:
            return "card"
    for hint in cfg.get("account_type_wallet_cash_hints") or []:
        if str(hint).lower() in name:
            return "wallet"
    return "card"


def is_cash_wallet_name(account_name: str) -> bool:
    cfg = get_nlu_config()
    name = (account_name or "").lower()
    for hint in cfg.get("account_type_wallet_cash_hints") or []:
        if str(hint).lower() in name:
            return True
    return False


def merge_write_context(parsed: dict, context: dict | None, *, enforce: bool) -> None:
    """Merge write context (badge, wizard). enforce=True overwrites NLU fields."""
    if not context:
        return
    for key, val in context.items():
        if key.startswith("_") or val is None:
            continue
        if enforce or not parsed.get(key):
            parsed[key] = val


async def get_or_create_account(session, user_id: int, account_name: Optional[str] = None) -> Account:
    """Find account by name or create; never substitute a random existing account."""
    if account_name:
        accounts = (
            await session.execute(select(Account).where(Account.user_id == user_id))
        ).scalars().all()

        matched = find_matching_label(account_name, [a.name for a in accounts])
        if matched:
            for acc in accounts:
                if labels_equal(acc.name, matched):
                    return acc

        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        account = Account(
            user_id=user_id,
            name=str(account_name).strip(),
            type=infer_account_type(account_name),
            currency=user.base_currency,
        )
        session.add(account)
        await session.flush()
        return account

    account = (
        await session.execute(select(Account).where(Account.user_id == user_id).limit(1))
    ).scalar_one_or_none()

    if not account:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        account = Account(
            user_id=user_id,
            name=dmsg(*_TC, "default_wallet"),
            type="wallet",
            currency=user.base_currency,
        )
        session.add(account)
        await session.flush()

    return account


async def resolve_expense_account(
    session,
    user_id: int,
    parsed: dict,
    *,
    badge_mode: bool = False,
) -> Account:
    """Expense/income account: badge account or parsed name."""
    if badge_mode:
        from bot.services.badge_tracker import BadgeTracker

        tracker = BadgeTracker()
        parsed["account"] = tracker.account_name
        parsed["category"] = parsed.get("category") or tracker.category
        parsed["_found_account_name"] = tracker.account_name
        return await tracker.get_or_create_badge_account(session, user_id)

    name = parsed.get("_found_account_name") or parsed.get("account")
    if not name:
        raise ValueError(dmsg(*_TC, "account_required"))
    return await get_or_create_account(session, user_id, name)


async def handle_broker_withdraw(session, user: User, parsed: dict, message: types.Message | None):
    """Broker withdraw flow (same as investments handler)."""
    nlu_cfg = get_nlu_config()
    broker_cats = nlu_cfg["broker_categories"]

    to_account = await get_or_create_account(session, user.id, parsed.get("to_account"))
    amount = Decimal(str(parsed["amount"]))
    fee = Decimal(str(parsed.get("fee", 0)))

    withdraw_category = broker_cats.get("withdraw") or dmsg(*_TC, "broker_withdraw_default")
    fee_category = broker_cats.get("fee") or dmsg(*_TC, "broker_fee_default")

    occurred = parse_occurred_at(parsed)
    session.add(
        Transaction(
            user_id=user.id,
            account_id=to_account.id,
            type="income",
            amount=amount,
            currency=to_account.currency,
            category=withdraw_category,
            description=withdraw_category,
            occurred_at=occurred,
        )
    )

    if fee > 0:
        session.add(
            Transaction(
                user_id=user.id,
                account_id=to_account.id,
                type="expense",
                amount=fee,
                currency=to_account.currency,
                category=fee_category,
                description=fee_category,
                occurred_at=occurred,
            )
        )

    await session.flush()


def format_transaction_response(parsed: dict, account: Account) -> str:
    """Format user-facing confirmation after save."""
    type_emoji = {
        "expense": "➖",
        "income": "➕",
        "transfer": "↔️",
        "debt_receivable": "💸",
        "debt_payable": "💸",
        "debt_settle_receivable": "💸",
    }
    emoji = type_emoji.get(parsed.get("type", ""), "💰")

    lines = [
        dmsg(
            *_TC,
            "recorded_header",
            emoji=emoji,
        )
    ]
    lines.append(
        dmsg(
            *_TC,
            "line_amount",
            amount=parsed["amount"],
            currency=parsed.get("currency", "RUB"),
        )
    )
    lines.append(dmsg(*_TC, "line_type", type=parsed["type"]))
    if parsed.get("category"):
        lines.append(dmsg(*_TC, "line_category", category=parsed["category"]))
    lines.append(dmsg(*_TC, "line_account", account=account.name))
    if parsed.get("description"):
        lines.append(dmsg(*_TC, "line_description", description=parsed["description"]))

    return "\n".join(lines)


async def get_missing_fields(parsed: dict, tg_id: int, *, badge_mode: bool = False) -> dict:
    """Return fields that need user selection (missing or unknown)."""
    missing = {}

    log.debug("checking transaction fields: %s", parsed)

    if parsed.get("type") in ["expense", "income"]:
        if not parsed.get("amount"):
            missing["amount"] = True
            log.warning("missing amount")
        else:
            log.info("amount ok: %s", parsed.get("amount"))

        category_name = parsed.get("category")
        if not category_name:
            missing["category"] = True
            log.warning("missing category")
        else:
            kind = "expense" if parsed.get("type") == "expense" else "income"
            available_categories = load_categories(kind)

            category_found = False
            found_cat = find_matching_label(category_name, available_categories)
            if found_cat:
                category_found = True
                parsed["_found_category_name"] = found_cat
                log.info("category ok: %s -> %s", category_name, found_cat)

            if not category_found:
                missing["category"] = True
                log.warning("category not in config: %s (%s)", category_name, kind)

        from bot.handlers.badge import transaction_uses_badge

        use_badge = transaction_uses_badge(parsed, badge_mode=badge_mode)
        if use_badge:
            from bot.services.badge_tracker import BadgeTracker

            tracker = BadgeTracker()
            parsed["account"] = tracker.account_name
            parsed["_found_account_name"] = tracker.account_name
            if not parsed.get("category"):
                parsed["category"] = tracker.category

        account_name = parsed.get("account")
        if not account_name:
            missing["account"] = True
            log.warning("missing account")
        elif use_badge:
            log.info("account ok (badge): %s", account_name)
        else:
            async with AsyncSessionLocal() as session:
                user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
                if not user:
                    missing["account"] = True
                    log.warning("user not found for tg_id=%s", tg_id)
                else:
                    accounts = (
                        await session.execute(select(Account).where(Account.user_id == user.id))
                    ).scalars().all()

                    account_found = False
                    found_acc = find_matching_label(account_name, [a.name for a in accounts])
                    if found_acc:
                        account_found = True
                        parsed["_found_account_name"] = found_acc
                        log.info("account ok: %s -> %s", account_name, found_acc)

                    if not account_found:
                        missing["account"] = True
                        log.warning("account not found: %s", account_name)

    elif parsed.get("type") == "transfer":
        if not parsed.get("amount"):
            missing["amount"] = True
        if not parsed.get("from_account"):
            missing["from_account"] = True
        if not parsed.get("to_account"):
            missing["to_account"] = True

    elif parsed.get("type") == "broker_withdraw":
        if not parsed.get("amount"):
            missing["amount"] = True
        if not parsed.get("to_account"):
            missing["to_account"] = True
        to_account_name = parsed.get("to_account")
        if to_account_name:
            async with AsyncSessionLocal() as session:
                user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
                if not user:
                    log.warning("user not found for broker_withdraw")
                    missing["to_account"] = True
                else:
                    accounts = (
                        await session.execute(select(Account).where(Account.user_id == user.id))
                    ).scalars().all()
                    account_found = False
                    found_to = find_matching_label(to_account_name, [a.name for a in accounts])
                    if found_to:
                        account_found = True
                        parsed["_found_to_account_name"] = found_to
                        log.info("to_account ok: %s -> %s", to_account_name, found_to)
                    if not account_found:
                        missing["to_account"] = True
                        log.warning("to_account not found: %s", to_account_name)

    elif parsed.get("type") == "debt_settle_receivable":
        if not parsed.get("amount"):
            missing["amount"] = True
        if not parsed.get("counterparty"):
            missing["counterparty"] = True
        account_name = parsed.get("account")
        if not account_name:
            missing["account"] = True
        else:
            async with AsyncSessionLocal() as session:
                user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
                if not user:
                    missing["account"] = True
                else:
                    accounts = (
                        await session.execute(
                            select(Account).where(
                                Account.user_id == user.id, Account.is_external_balance == False
                            )
                        )
                    ).scalars().all()
                    found_acc = find_matching_label(account_name, [a.name for a in accounts])
                    if found_acc:
                        parsed["_found_account_name"] = found_acc
                    if not found_acc:
                        missing["account"] = True

    elif parsed.get("type") in ["debt_receivable", "debt_payable"]:
        if not parsed.get("amount"):
            missing["amount"] = True
        if not parsed.get("counterparty"):
            missing["counterparty"] = True
        if parsed.get("type") == "debt_receivable" and not parsed.get("account"):
            missing["account"] = True
        elif not parsed.get("account"):
            async with AsyncSessionLocal() as session:
                user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
                if not user:
                    missing["account"] = True
                    log.warning("user not found for debt")
                else:
                    accounts = (
                        await session.execute(select(Account).where(Account.user_id == user.id).limit(1))
                    ).scalars().all()
                    if not accounts:
                        missing["account"] = True
                    else:
                        default_account = accounts[0]
                        parsed["account"] = default_account.name
                        parsed["_found_account_name"] = default_account.name
                        log.info("debt default account: %s", default_account.name)

    return missing
