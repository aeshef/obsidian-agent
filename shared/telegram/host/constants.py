"""Host UI modes and domain ids (single-bot)."""
from __future__ import annotations

UI_MODE_AUTO = "auto"
DOMAIN_FINANCE = "finance"
DOMAIN_PLANNING = "planning"
DOMAIN_KNOWLEDGE = "knowledge"
DOMAIN_UNIFIED = "unified"  # agent loop: merged tools (LLM host_domain_router)
DOMAIN_GENERAL = "general"  # host_domain_router: outside finance/planning/knowledge

DOMAIN_IDS = frozenset({DOMAIN_FINANCE, DOMAIN_PLANNING, DOMAIN_KNOWLEDGE})

KB_QUERY_PENDING_KEY = "kb_query_pending"
