"""Host UI modes, domain ids, and shared env-backed defaults."""
from __future__ import annotations

import os
from datetime import datetime


def deepseek_chat_completions_url() -> str:
    return os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")


def deepseek_model() -> str:
    return os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")


def goals_year() -> int:
    raw = (os.environ.get("GOALS_YEAR") or "").strip()
    if raw.isdigit():
        return int(raw)
    return datetime.now().year


UI_MODE_AUTO = "auto"
DOMAIN_FINANCE = "finance"
DOMAIN_PLANNING = "planning"
DOMAIN_KNOWLEDGE = "knowledge"
DOMAIN_UNIFIED = "unified"  # agent loop: merged tools (LLM host_domain_router)
DOMAIN_GENERAL = "general"  # host_domain_router: outside finance/planning/knowledge

DOMAIN_IDS = frozenset({DOMAIN_FINANCE, DOMAIN_PLANNING, DOMAIN_KNOWLEDGE})

KB_QUERY_PENDING_KEY = "kb_query_pending"
