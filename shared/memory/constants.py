"""Memory domain ids for insights and session history."""
from __future__ import annotations

GLOBAL_DOMAIN = "global"

AGENT_DOMAINS = ("finance", "planning", "knowledge")
SESSION_DOMAINS = (*AGENT_DOMAINS, "unified")
