"""Resolve outbound proxy for OpenRouter (vision + embeddings).

Uses the same proxy chain as YouTube ingest when OPENROUTER_PROXY is unset.
"""
from __future__ import annotations

import os


def openrouter_proxy_url(*, override: str | None = None) -> str | None:
    """First non-empty proxy URL from env (OPENROUTER_PROXY → YOUTUBE_PROXY → HTTPS/HTTP)."""
    if override is not None and override.strip():
        return override.strip()
    for key in ("OPENROUTER_PROXY", "YOUTUBE_PROXY", "HTTPS_PROXY", "HTTP_PROXY"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw
    return None


def openrouter_requests_proxies(*, override: str | None = None) -> dict[str, str] | None:
    url = openrouter_proxy_url(override=override)
    if not url:
        return None
    return {"http": url, "https": url}
