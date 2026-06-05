"""
Broker portfolio account type helpers (T-Invest API sync vs manual broker YAML).

Only type == broker_portfolio — account from Invest API sync (snapshots, broker line in dashboard).

Accounts with type == broker from YAML/manual entry are other brokers, not T-Invest API:
do not mix with Tinkoff portfolio (counted as other external RUB in totals).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Optional

from shared.finance.broker_sync_config import load_broker_sync_yaml

BROKER_PORTFOLIO_ACCOUNT_TYPE: Final[str] = "broker_portfolio"
BROKER_YAML_ACCOUNT_TYPE: Final[str] = "broker"


def _broker_sync_config() -> dict:
    return load_broker_sync_yaml()


def _legacy_orphan_names() -> frozenset[str]:
    legacy = _broker_sync_config().get("legacy") or {}
    items = legacy.get("orphan_names") or []
    return frozenset(str(x) for x in items)


def _legacy_suffixed_prefixes() -> tuple[str, ...]:
    legacy = _broker_sync_config().get("legacy") or {}
    items = legacy.get("suffixed_prefixes") or []
    return tuple(str(x) for x in items)


@dataclass(frozen=True)
class BrokerSyncLabelTemplates:
    regular: str
    iis: str
    invest_box: str


def broker_sync_label_templates() -> BrokerSyncLabelTemplates:
    labels = _broker_sync_config().get("labels") or {}
    return BrokerSyncLabelTemplates(
        regular=str(labels.get("regular") or ""),
        iis=str(labels.get("iis") or ""),
        invest_box=str(labels.get("invest_box") or ""),
    )


def is_broker_portfolio_account(account_type: Optional[str], is_external_balance: bool) -> bool:
    """Invest API only (post-sync type); not type=broker from YAML for other custodians."""
    if not is_external_balance:
        return False
    t = (account_type or "").strip()
    return t == BROKER_PORTFOLIO_ACCOUNT_TYPE


def format_portfolio_account_label(
    api_account_type_name: Optional[str],
    account_id: str,
    templates: BrokerSyncLabelTemplates,
) -> str:
    """
    Stable account name in DB (no id suffix). Identity — external_ref = API account_id.
    """
    _ = account_id
    if api_account_type_name == "ACCOUNT_TYPE_TINKOFF_IIS":
        tpl = templates.iis
    elif api_account_type_name == "ACCOUNT_TYPE_INVEST_BOX":
        tpl = templates.invest_box
    else:
        tpl = templates.regular
    label = tpl.replace("{suffix}", "").strip()
    return label


def legacy_orphan_portfolio_names() -> frozenset[str]:
    return _legacy_orphan_names()


def is_legacy_suffixed_portfolio_name(name: str) -> bool:
    n = (name or "").strip()
    orphans = _legacy_orphan_names()
    prefixes = _legacy_suffixed_prefixes()
    if n in orphans:
        return True
    return any(n.startswith(p) and len(n) > len(p) for p in prefixes)
