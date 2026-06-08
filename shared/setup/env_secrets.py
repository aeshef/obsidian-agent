"""Detect placeholder secrets and optionally ping DeepSeek API."""
from __future__ import annotations

import os
import re
from typing import Optional

_PLACEHOLDER_FRAGMENTS = (
    "sk-...",
    "your_",
    "your-",
    "changeme",
    "placeholder",
    "xxx",
    "todo",
    "fill",
    "example",
)

_TELEGRAM_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{20,}$")


def is_placeholder_secret(key: str, value: Optional[str]) -> bool:
    v = (value or "").strip().strip('"').strip("'")
    if not v:
        return True
    low = v.lower()
    if any(p in low for p in _PLACEHOLDER_FRAGMENTS):
        return True
    if key in ("DEEPSEEK_API_KEY", "DEEPSEEK_API_TOKEN"):
        if not v.startswith("sk-") or len(v) < 20:
            return True
    if key in ("TELEGRAM_UNIFIED_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_KNOWLEDGE_BOT_TOKEN"):
        if not _TELEGRAM_RE.match(v):
            return True
    if key == "OPENROUTER_API_KEY" and (not v.startswith("sk-") or len(v) < 20):
        return True
    return False


def resolve_deepseek_key() -> str:
    return (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_TOKEN") or "").strip()


def ping_deepseek(timeout: float = 15.0) -> tuple[bool, str]:
    """Minimal API call; returns (ok, message)."""
    key = resolve_deepseek_key()
    if is_placeholder_secret("DEEPSEEK_API_KEY", key):
        return False, "DEEPSEEK_API_KEY missing or still .env.example placeholder"
    try:
        import requests
    except ImportError:
        return False, "requests not installed (run ./scripts/setup.sh)"

    base = (os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1").rstrip("/")
    model = (os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat").strip()
    url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except Exception as e:
        return False, f"DeepSeek network error: {e}"
    if resp.status_code == 401:
        return False, "DeepSeek 401 — API key invalid (get a new key at platform.deepseek.com)"
    if resp.status_code >= 400:
        return False, f"DeepSeek HTTP {resp.status_code}: {resp.text[:200]}"
    return True, "DeepSeek API key OK"


def validate_core_secrets(
    *,
    ping_deepseek_api: bool = False,
    require_openrouter: bool = False,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for key in ("VAULT_PATH", "TELEGRAM_UNIFIED_BOT_TOKEN", "DEEPSEEK_API_KEY"):
        val = os.environ.get(key) or ""
        if key == "TELEGRAM_UNIFIED_BOT_TOKEN" and not val.strip():
            val = os.environ.get("TELEGRAM_BOT_TOKEN") or ""
        if is_placeholder_secret(key, val):
            errors.append(f"{key}: not set or still placeholder (.env.example value)")
    if ping_deepseek_api:
        ok, msg = ping_deepseek()
        if not ok:
            errors.append(msg)
    elif is_placeholder_secret("DEEPSEEK_API_KEY", resolve_deepseek_key()):
        errors.append("DEEPSEEK_API_KEY: set a real key (required for NLU and chat)")
    if require_openrouter:
        if is_placeholder_secret("OPENROUTER_API_KEY", os.environ.get("OPENROUTER_API_KEY")):
            errors.append("OPENROUTER_API_KEY: required for knowledge module")
    return errors, warnings
