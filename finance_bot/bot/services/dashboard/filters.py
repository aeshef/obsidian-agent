"""Category / badge / exclude predicates for finance dashboard charts."""
from __future__ import annotations

import os
from typing import Mapping, Optional


def resolve_exclude_spending_categories() -> set[str]:
    """Categories excluded from spending/income analytics (env override or shared defaults)."""
    exclude_cats_raw = os.environ.get("FIN_EXCLUDE_FROM_SPENDING_CATEGORIES", "")
    if not exclude_cats_raw.strip():
        from shared.finance_classification import exclude_spending_categories as _excl

        return set(_excl())
    return {c.strip() for c in exclude_cats_raw.split(",") if c.strip()}


def resolve_badge_category() -> Optional[str]:
    from bot.config_loader import get_badge_config, is_badge_enabled

    if not is_badge_enabled():
        return None
    cat = str(get_badge_config().get("category") or "")
    return cat or None


def resolve_badge_account_name() -> str:
    from bot.config_loader import get_badge_config, is_badge_enabled

    if not is_badge_enabled():
        return ""
    return str(get_badge_config().get("account_name", "Meal Badge"))


def is_excluded_category(txn: Mapping, exclude_categories: set[str]) -> bool:
    cat = (txn.get("category") or "").strip()
    return bool(cat) and cat in exclude_categories


def is_badge_expense(txn: Mapping, badge_category: Optional[str]) -> bool:
    return bool(badge_category) and (txn.get("category") or "") == badge_category


def skip_badge_account(
    aid: int,
    acc_by_id: Mapping[int, Mapping],
    badge_account_name: str,
) -> bool:
    if not badge_account_name:
        return False
    return acc_by_id.get(aid, {}).get("name") == badge_account_name
