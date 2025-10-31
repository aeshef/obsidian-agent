from datetime import date
from decimal import Decimal
from typing import Any, List
import logging
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User, Account, AccountBalanceSnapshot, Transaction
from ..config import get_settings
from ..broker_portfolio import (
    BROKER_PORTFOLIO_ACCOUNT_TYPE,
    BrokerSyncLabelTemplates,
    broker_sync_label_templates,
    format_portfolio_account_label,
    is_legacy_suffixed_portfolio_name,
    legacy_orphan_portfolio_names,
)
from shared.domain_messages import dmsg
from shared.finance.broker_sync_config import broker_account_sync_enabled

log = logging.getLogger("finance.tinkoff")


def _money_value_to_decimal(q) -> Decimal:
    if q is None:
        return Decimal("0")
    return Decimal(str((q.units or 0))) + (Decimal(str(q.nano or 0)) / Decimal("1000000000"))


def _label_templates_from_settings(_settings: Any) -> BrokerSyncLabelTemplates:
    return broker_sync_label_templates()


def _fetch_tinkoff_summary(token: str) -> dict:
    """Load REST wrapper from tools/tinkoff_sync.py."""
    import sys
    from pathlib import Path

    tools_dir = Path(__file__).resolve().parent.parent.parent / "tools"
    sd = str(tools_dir)
    if sd not in sys.path:
        sys.path.insert(0, sd)
    from tinkoff_sync import fetch_tinkoff_summary  # type: ignore

    return fetch_tinkoff_summary(token)


async def _upsert_external_account(
    session: AsyncSession,
    user_id: int,
    name: str,
    balance_rub: Decimal,
    external_ref: str,
) -> Account:
    ref = (external_ref or "").strip()
    acc = None
    if ref:
        acc = (
            await session.execute(
                select(Account).where(Account.user_id == user_id, Account.external_ref == ref)
            )
        ).scalar_one_or_none()
    # Fallback by name only when external_ref is missing (legacy rows).
    if acc is None and not ref:
        acc = (
            await session.execute(select(Account).where(Account.user_id == user_id, Account.name == name))
        ).scalar_one_or_none()
    if acc is None:
        acc = Account(
            user_id=user_id,
            name=name,
            external_ref=ref or None,
            type=BROKER_PORTFOLIO_ACCOUNT_TYPE,
            currency="RUB",
            is_external_balance=True,
            external_balance=balance_rub,
        )
        session.add(acc)
    else:
        acc.name = name
        acc.external_ref = ref or acc.external_ref
        acc.type = BROKER_PORTFOLIO_ACCOUNT_TYPE
        acc.is_external_balance = True
        acc.external_balance = balance_rub
    return acc


async def _save_balance_snapshot(session: AsyncSession, account_id: int, balance_rub: Decimal) -> None:
    today = date.today()
    existing = (
        await session.execute(
            select(AccountBalanceSnapshot).where(
                AccountBalanceSnapshot.account_id == account_id,
                AccountBalanceSnapshot.snapshot_date == today,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.balance = balance_rub
    else:
        session.add(
            AccountBalanceSnapshot(account_id=account_id, snapshot_date=today, balance=balance_rub)
        )


def _map_sdk_account_label(account_obj: Any, templates: BrokerSyncLabelTemplates) -> str:
    t = getattr(account_obj, "type", None)
    t_name = getattr(t, "name", None) if t is not None else None
    acc_id = getattr(account_obj, "id", "") or ""
    return format_portfolio_account_label(t_name if isinstance(t_name, str) else None, acc_id, templates)


async def _account_tx_count(session: AsyncSession, account_id: int) -> int:
    n_tx = (
        await session.execute(
            select(func.count()).select_from(Transaction).where(Transaction.account_id == account_id)
        )
    ).scalar_one()
    return int(n_tx or 0)


async def _delete_portfolio_account_if_orphan(session: AsyncSession, acc: Account) -> bool:
    if await _account_tx_count(session, acc.id) > 0:
        log.warning(
            "Portfolio account id=%s name=%r has transactions; skipped auto-removal",
            acc.id,
            acc.name,
        )
        return False
    await session.delete(acc)
    return True


async def _drop_legacy_orphan_portfolio_rows(session: AsyncSession, user_id: int) -> None:
    """Drop legacy broker_portfolio rows without external_ref."""
    rows = (
        await session.execute(
            select(Account).where(
                Account.user_id == user_id,
                Account.type == BROKER_PORTFOLIO_ACCOUNT_TYPE,
                Account.is_external_balance.is_(True),
            )
        )
    ).scalars().all()
    for acc in rows:
        if acc.external_ref:
            continue
        if not is_legacy_suffixed_portfolio_name(acc.name) and acc.name not in legacy_orphan_portfolio_names():
            continue
        if await _delete_portfolio_account_if_orphan(session, acc):
            await session.flush()


async def _prune_stale_portfolio_accounts(
    session: AsyncSession, user_id: int, active_refs: set[str]
) -> None:
    """Remove stale T-Invest portfolio accounts absent from API with no transactions."""
    rows = (
        await session.execute(
            select(Account).where(
                Account.user_id == user_id,
                Account.type == BROKER_PORTFOLIO_ACCOUNT_TYPE,
                Account.is_external_balance.is_(True),
            )
        )
    ).scalars().all()
    for acc in rows:
        ref = (acc.external_ref or "").strip()
        if not ref or ref in active_refs:
            continue
        if await _delete_portfolio_account_if_orphan(session, acc):
            log.info("Removed stale Tinkoff portfolio account id=%s ref=%s name=%r", acc.id, ref, acc.name)
            await session.flush()


async def _sync_via_sdk(session: AsyncSession, user: User, token: str) -> str:
    from tinkoff.invest import Client

    lines: List[str] = []
    total = Decimal("0")
    settings = get_settings()
    templates = _label_templates_from_settings(settings)
    ignore_ids: set[str] = set()
    if settings.TINKOFF_IGNORE_ACCOUNT_IDS:
        ignore_ids = {x.strip() for x in settings.TINKOFF_IGNORE_ACCOUNT_IDS.split(",") if x.strip()}
    await _drop_legacy_orphan_portfolio_rows(session, user.id)
    active_refs: set[str] = set()
    with Client(token) as client:
        accs = client.users.get_accounts().accounts
        for a in accs:
            acc_id = str(getattr(a, "id", "") or "")
            if acc_id in ignore_ids:
                continue
            t = getattr(a, "type", None)
            t_name = getattr(t, "name", None) if t is not None else None
            if not broker_account_sync_enabled(t_name if isinstance(t_name, str) else None):
                continue
            active_refs.add(acc_id)
            p = client.operations.get_portfolio(account_id=a.id)
            q = p.total_amount_portfolio
            cur = (q.currency or "").upper()
            if cur and cur not in ("RUB", "RUR"):
                log.warning(
                    "total_amount_portfolio currency is %s, not RUB; value stored without conversion",
                    q.currency,
                )
            value = _money_value_to_decimal(q)
            name = _map_sdk_account_label(a, templates)
            acc = await _upsert_external_account(session, user.id, name, value, acc_id)
            await session.flush()
            await _save_balance_snapshot(session, acc.id, value)
            lines.append(f"{name:<32} {value:>14} RUB")
            total += value
        await _prune_stale_portfolio_accounts(session, user.id, active_refs)
        await session.commit()
    body = "\n".join(lines)
    if not lines:
        raise RuntimeError(dmsg("finance_tinkoff", "no_accounts"))
    return f"<pre>\n{body}\n\n{dmsg('finance_tinkoff', 'total_line', total=total)}\n</pre>"


async def _sync_via_rest(session: AsyncSession, user: User, token: str) -> str:
    data = _fetch_tinkoff_summary(token)
    dbg = data.get("_debug", {})
    equities: dict = dbg.get("equities", {}) or {}
    account_types: dict = dbg.get("account_types", {}) or {}
    total_rub = data.get("total_rub", 0)
    lines: List[str] = []
    total = Decimal("0")
    settings = get_settings()
    templates = _label_templates_from_settings(settings)
    ignore_ids: set[str] = set()
    if settings.TINKOFF_IGNORE_ACCOUNT_IDS:
        ignore_ids = {x.strip() for x in settings.TINKOFF_IGNORE_ACCOUNT_IDS.split(",") if x.strip()}
    await _drop_legacy_orphan_portfolio_rows(session, user.id)
    active_refs: set[str] = set()
    for acc_id, val in equities.items():
        sid = str(acc_id)
        if sid in ignore_ids:
            continue
        api_type = account_types.get(sid) or account_types.get(acc_id)
        if not broker_account_sync_enabled(api_type if isinstance(api_type, str) else None):
            continue
        active_refs.add(sid)
        name = format_portfolio_account_label(
            api_type if isinstance(api_type, str) else None,
            sid,
            templates,
        )
        balance = Decimal(str(val))
        acc = await _upsert_external_account(session, user.id, name, balance, sid)
        await session.flush()
        await _save_balance_snapshot(session, acc.id, balance)
        lines.append(f"{name:<32} {balance:>14} RUB")
        total += balance
    if total_rub > 0 and not lines:
        name = format_portfolio_account_label("ACCOUNT_TYPE_TINKOFF", "", templates)
        balance = Decimal(str(total_rub))
        acc = await _upsert_external_account(session, user.id, name, balance, "aggregate")
        active_refs.add("aggregate")
        await session.flush()
        await _save_balance_snapshot(session, acc.id, balance)
        lines.append(f"{name:<32} {balance:>14} RUB")
        total = balance
    await _prune_stale_portfolio_accounts(session, user.id, active_refs)
    await session.commit()
    body = "\n".join(lines)
    if not lines:
        raise RuntimeError(dmsg("finance_tinkoff", "no_portfolio_data", keys=list(dbg.keys())))
    return f"<pre>\n{body}\n\n{dmsg('finance_tinkoff', 'total_line', total=total)}\n</pre>"


async def sync_tinkoff_account(session: AsyncSession, user: User) -> str:
    settings = get_settings()
    if not settings.TINKOFF_API_TOKEN:
        raise ValueError(dmsg("finance_tinkoff", "token_missing"))

    try:
        text = await _sync_via_sdk(session, user, settings.TINKOFF_API_TOKEN)
    except ModuleNotFoundError as e:
        log.info("Invest SDK unavailable (%s), using REST fallback", type(e).__name__)
        text = await _sync_via_rest(session, user, settings.TINKOFF_API_TOKEN)
    return text


def tinkoff_debug_text() -> str:
    settings = get_settings()
    if not settings.TINKOFF_API_TOKEN:
        raise ValueError(dmsg("finance_tinkoff", "token_missing"))
    templates = _label_templates_from_settings(settings)
    data = _fetch_tinkoff_summary(settings.TINKOFF_API_TOKEN)
    dbg = data.get("_debug", {})
    equities: dict = dbg.get("equities", {}) or {}
    account_types: dict = dbg.get("account_types", {}) or {}
    total_rub = data.get("total_rub", 0)
    accounts = dbg.get("accounts_rest", []) or dbg.get("accounts_v2", [])
    errors = [e for e in dbg.get("errors", []) if "import_error" not in str(e) and "tg_alerting" not in str(e)]
    lines = ["<pre>"]
    if equities:
        tot = 0.0
        for acc_id, val in equities.items():
            sid = str(acc_id)
            api_type = account_types.get(sid) or account_types.get(acc_id)
            name = format_portfolio_account_label(
                api_type if isinstance(api_type, str) else None,
                sid,
                templates,
            )
            lines.append(f"{name:<32} {float(val):>14,.2f} RUB")
            tot += float(val)
        lines.append("")
        lines.append(dmsg("finance_tinkoff", "total_fmt", total=tot))
    elif total_rub > 0:
        lines.append(dmsg("finance_tinkoff", "portfolio_total_rub", total=total_rub))
    elif accounts:
        lines.append(dmsg("finance_tinkoff", "api_accounts_count", count=len(accounts)))
        lines.append(dmsg("finance_tinkoff", "no_positions"))
    else:
        lines.append(dmsg("finance_tinkoff", "no_portfolio"))
        if errors:
            lines.append("")
            lines.append(dmsg("finance_tinkoff", "errors_prefix", errors="; ".join(str(e)[:100] for e in errors[:3])))
    lines.append("</pre>")
    return "\n".join(lines)
