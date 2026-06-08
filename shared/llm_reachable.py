"""DNS preflight for DeepSeek API availability before LLM-dependent steps.

Moved from knowledge_bot/services/llm_reachable.py — domain-agnostic,
used by all bots and obsidian_sync.
"""
from __future__ import annotations

import socket

from shared.constants import deepseek_base_url
from urllib.parse import urlparse


def deepseek_host_from_env() -> str:
    base = deepseek_base_url().strip()
    parsed = urlparse(base if "://" in base else f"https://{base}")
    return (parsed.hostname or "api.deepseek.com").lower()


def deepseek_api_reachable(timeout: float | None = None) -> bool:
    """True if API host resolves (DNS). No HTTP — getaddrinfo only."""
    if timeout is None:
        from shared.platform_timeouts import llm_reachable_timeout_sec

        timeout = llm_reachable_timeout_sec()
    host = deepseek_host_from_env()
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return True
    except OSError:
        return False


def is_garbage_fallback_title(title: str) -> bool:
    """Title from LLM fallback JSON payload (reprocess artifact on network drop)."""
    t = (title or "").strip()
    if not t:
        return False
    if t.startswith("{") or t.startswith('{"'):
        return True
    low = t.lower()
    if "summary" in low and ("raw_text" in low or '"type"' in low or "derive" in low):
        return True
    if len(t) > 50 and "meta" in low and "form" in low:
        return True
    return False
