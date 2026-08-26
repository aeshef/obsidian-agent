"""Load finance_bot/config/broker_sync.yaml (example fallback) — no secrets."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from shared.capabilities.features import broker_api_kind, feature_enabled
from shared.capabilities.profile import _as_bool
from shared.yaml_config import load_merged_config


def _finance_config_dir() -> Path:
    root = os.environ.get("AGENT_ROOT", "").strip()
    if root:
        return Path(root) / "finance_bot" / "config"
    return Path(__file__).resolve().parents[2] / "finance_bot" / "config"


@lru_cache(maxsize=1)
def load_broker_sync_yaml() -> dict:
    return load_merged_config(str(_finance_config_dir()), "broker_sync")


def broker_sync_provider() -> str:
    raw = str(load_broker_sync_yaml().get("provider") or "none").strip().lower()
    return raw or "none"


def broker_account_yaml_enabled(kind: str) -> bool:
    accounts = load_broker_sync_yaml().get("accounts")
    if not isinstance(accounts, dict) or kind not in accounts:
        return True
    return _as_bool(accounts.get(kind), True)


def broker_account_sync_enabled(api_type_name: Optional[str] = None) -> bool:
    feat = broker_api_kind(api_type_name)
    if not feature_enabled(feat):
        return False
    yaml_kind = feat.removeprefix("broker_")
    return broker_account_yaml_enabled(yaml_kind)
