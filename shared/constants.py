"""Monorepo defaults (env overrides) and host domain ids."""
from __future__ import annotations

import os
from datetime import datetime

DEFAULT_TIMEZONE = "UTC"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"

UI_MODE_AUTO = "auto"
DOMAIN_FINANCE = "finance"
DOMAIN_PLANNING = "planning"
DOMAIN_KNOWLEDGE = "knowledge"
DOMAIN_UNIFIED = "unified"
DOMAIN_GENERAL = "general"

DOMAIN_IDS = frozenset({DOMAIN_FINANCE, DOMAIN_PLANNING, DOMAIN_KNOWLEDGE})

KB_QUERY_PENDING_KEY = "kb_query_pending"


def timezone_name(*, override: str | None = None) -> str:
    if override and override.strip():
        return override.strip()
    return (os.environ.get("TIMEZONE") or DEFAULT_TIMEZONE).strip()


def deepseek_base_url(*, override: str | None = None) -> str:
    raw = (override or os.environ.get("DEEPSEEK_BASE_URL") or DEFAULT_DEEPSEEK_BASE_URL).strip()
    base = raw.rstrip("/")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")].rstrip("/")
    return base


def deepseek_chat_completions_url(*, override: str | None = None) -> str:
    base = deepseek_base_url(override=override)
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def deepseek_model(*, override: str | None = None) -> str:
    return (override or os.environ.get("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL).strip()


def goals_year(*, override: str | None = None) -> int:
    raw = (override or os.environ.get("GOALS_YEAR") or str(datetime.now().year)).strip()
    try:
        return int(raw)
    except ValueError:
        return datetime.now().year


def finance_dashboard_start_date(*, override: str | None = None) -> str:
    raw = (override or os.environ.get("FIN_DASHBOARD_START_DATE") or "").strip()
    if raw:
        return raw
    return f"{datetime.now().year}-01-01"
