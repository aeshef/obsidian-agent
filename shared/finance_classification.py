"""
Transaction classification for analytics and dashboard.

Consumption — expenses where money leaves aggregate capital.
Override: env FIN_EXCLUDE_FROM_SPENDING_CATEGORIES / FIN_EXCLUDE_FROM_INCOME_CATEGORIES
or finance_bot/config/analytics_categories.yaml (over .example).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Mapping, Tuple

from shared.domain_messages import dmsg
from shared.yaml_config import load_merged_config


def uncategorized_label() -> str:
    return dmsg("finance", "uncategorized")


def misc_category_label() -> str:
    return dmsg("finance", "misc")


def transfer_substring() -> str:
    return dmsg("finance", "transfer_substring")

_FINANCE_CFG = Path(__file__).resolve().parent.parent / "finance_bot" / "config"


@lru_cache(maxsize=1)
def _analytics_categories() -> dict:
    return load_merged_config(str(_FINANCE_CFG), "analytics_categories")


def _csv_set(key: str, env_name: str) -> frozenset[str]:
    raw = os.environ.get(env_name)
    if raw is None or not str(raw).strip():
        raw = str(_analytics_categories().get(key) or "")
    return frozenset(c.strip() for c in str(raw).split(",") if c.strip())


def exclude_spending_categories() -> frozenset[str]:
    return _csv_set("exclude_spending", "FIN_EXCLUDE_FROM_SPENDING_CATEGORIES")


def exclude_income_categories() -> frozenset[str]:
    return _csv_set("exclude_income", "FIN_EXCLUDE_FROM_INCOME_CATEGORIES")


def investment_expense_categories() -> frozenset[str]:
    env_raw = os.environ.get("FIN_INVESTMENT_EXPENSE_CATEGORIES")
    if env_raw and str(env_raw).strip():
        return frozenset(c.strip() for c in env_raw.split(",") if c.strip())
    items = _analytics_categories().get("investment_expense")
    if isinstance(items, list):
        return frozenset(str(x).strip() for x in items if str(x).strip())
    return frozenset()


INVESTMENT_EXPENSE_CATEGORIES = investment_expense_categories()


def txn_category(txn: Mapping) -> str:
    return (txn.get("category") or "").strip()


def is_internal_move_expense(txn: Mapping) -> bool:
    return txn.get("type") == "expense" and txn_category(txn) in exclude_spending_categories()


def is_internal_move_income(txn: Mapping) -> bool:
    return txn.get("type") == "income" and txn_category(txn) in exclude_income_categories()


def is_investment_expense(txn: Mapping) -> bool:
    cat = txn_category(txn)
    return txn.get("type") == "expense" and (
        cat in INVESTMENT_EXPENSE_CATEGORIES or cat in exclude_spending_categories()
    )


def is_consumption_expense(txn: Mapping) -> bool:
    if txn.get("type") != "expense":
        return False
    cat = txn_category(txn)
    if cat in exclude_spending_categories():
        return False
    if cat in INVESTMENT_EXPENSE_CATEGORIES:
        return False
    return True


def is_real_income(txn: Mapping) -> bool:
    if txn.get("type") != "income":
        return False
    return txn_category(txn) not in exclude_income_categories()


def split_month_flows(
    month_txns: List[Mapping],
) -> Tuple[float, float, float, float, Dict[str, float]]:
    """
    (real_income, consumption, investments, internal_transfers_volume, consumption_by_category)

    internal_transfers_volume — sum of outgoing Transfer legs (reference only, not consumption).
    """
    real_income = 0.0
    consumption = 0.0
    investments = 0.0
    transfers_out = 0.0
    cat_totals: Dict[str, float] = {}
    transfer_labels = {
        c for c in exclude_spending_categories() if transfer_substring() in c.lower()
    }

    for t in month_txns:
        amt = float(t.get("amount") or 0)
        if is_real_income(t):
            real_income += amt
        if not is_consumption_expense(t):
            if t.get("type") != "expense":
                continue
            cat = txn_category(t)
            if cat in transfer_labels:
                transfers_out += amt
            elif cat in INVESTMENT_EXPENSE_CATEGORIES:
                investments += amt
            continue
        cat = txn_category(t) or uncategorized_label()
        consumption += amt
        cat_totals[cat] = cat_totals.get(cat, 0.0) + amt

    return real_income, consumption, investments, transfers_out, cat_totals
