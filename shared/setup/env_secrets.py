"""Detect placeholder secrets and optionally ping the chat LLM API."""
from __future__ import annotations

import os
import re
from typing import Optional

from shared.constants import deepseek_base_url, deepseek_model, llm_api_key

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

_LLM_KEY_NAMES = frozenset(
    {"LLM_API_KEY", "DEEPSEEK_API_KEY", "DEEPSEEK_API_TOKEN"}
)


def is_placeholder_secret(key: str, value: Optional[str]) -> bool:
    v = (value or "").strip().strip('"').strip("'")
    if not v:
        return True
    low = v.lower()
    if any(p in low for p in _PLACEHOLDER_FRAGMENTS):
        return True
    if key in _LLM_KEY_NAMES:
        # OpenAI-style keys are usually sk-…; local/vLLM may use other tokens — only
        # reject obvious placeholders and extremely short values.
        if len(v) < 8:
            return True
        if v.startswith("sk-") and len(v) < 20:
            return True
    if key in ("TELEGRAM_UNIFIED_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_KNOWLEDGE_BOT_TOKEN"):
        if not _TELEGRAM_RE.match(v):
            return True
    if key == "OPENROUTER_API_KEY" and (not v.startswith("sk-") or len(v) < 20):
        return True
    return False


def resolve_deepseek_key() -> str:
    """Resolved chat LLM API key (LLM_* or legacy DEEPSEEK_*)."""
    return llm_api_key() or ""


def resolve_llm_key() -> str:
    return resolve_deepseek_key()


def ping_deepseek(timeout: float = 15.0) -> tuple[bool, str]:
    """Minimal chat/completions call; returns (ok, message)."""
    key = resolve_llm_key()
    if is_placeholder_secret("LLM_API_KEY", key):
        return False, "LLM_API_KEY / DEEPSEEK_API_KEY missing or still .env.example placeholder"
    try:
        import requests
    except ImportError:
        return False, "requests not installed (run ./scripts/setup.sh)"

    base = deepseek_base_url()
    model = deepseek_model()
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
        return False, f"LLM network error: {e}"
    if resp.status_code == 401:
        return False, "LLM 401 — API key invalid for LLM_BASE_URL host"
    if resp.status_code >= 400:
        return False, f"LLM HTTP {resp.status_code}: {resp.text[:200]}"
    return True, f"LLM API key OK ({model} @ {base})"


def validate_core_secrets(
    *,
    ping_deepseek_api: bool = False,
    require_openrouter: bool = False,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    vault = os.environ.get("VAULT_PATH") or ""
    if is_placeholder_secret("VAULT_PATH", vault):
        errors.append("VAULT_PATH: not set or still placeholder (.env.example value)")
    tg = os.environ.get("TELEGRAM_UNIFIED_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or ""
    if is_placeholder_secret("TELEGRAM_UNIFIED_BOT_TOKEN", tg):
        errors.append("TELEGRAM_UNIFIED_BOT_TOKEN: not set or still placeholder")
    llm = resolve_llm_key()
    if is_placeholder_secret("LLM_API_KEY", llm):
        errors.append("LLM_API_KEY (or DEEPSEEK_API_KEY): set a real key for NLU and chat")
    if ping_deepseek_api:
        ok, msg = ping_deepseek()
        if not ok:
            errors.append(msg)
    if require_openrouter:
        if is_placeholder_secret("OPENROUTER_API_KEY", os.environ.get("OPENROUTER_API_KEY")):
            errors.append("OPENROUTER_API_KEY: required for knowledge module")
    return errors, warnings
