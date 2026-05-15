from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

_lock: threading.Lock | None = None
_last_request_at: float = 0.0


def _get_lock() -> threading.Lock:
    global _lock
    if _lock is None:
        _lock = threading.Lock()
    return _lock


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def wait_before_openrouter_request() -> None:
    """English docstring omitted (see domain_messages.yaml)."""
    min_interval = _env_float("OPENROUTER_MIN_INTERVAL_SECONDS", 4.0)
    if min_interval <= 0:
        return
    global _last_request_at
    with _get_lock():
        now = time.monotonic()
        wait_s = min_interval - (now - _last_request_at)
        if wait_s > 0:
            time.sleep(wait_s)
        _last_request_at = time.monotonic()


def _retry_wait_seconds(response: Any, attempt: int, base_backoff: float) -> float:
    retry_after = getattr(response, "headers", {}).get("Retry-After")
    if retry_after:
        try:
            return max(base_backoff * (2**attempt), float(retry_after))
        except ValueError:
            pass
    return base_backoff * (2**attempt)


def openrouter_post(
    url: str,
    *,
    headers: dict[str, str],
    json_payload: dict[str, Any],
    timeout: float = 90.0,
    max_retries: int | None = None,
) -> Any:
    """Module helper (user strings in YAML)."""
    import requests as requests_mod

    log = logging.getLogger("kb.openrouter")
    if max_retries is None:
        max_retries = _env_int("OPENROUTER_429_MAX_RETRIES", 4)
    base_backoff = _env_float("OPENROUTER_429_BACKOFF_SECONDS", 8.0)
    retryable = frozenset({429, 503})

    last: Any = None
    for attempt in range(max_retries + 1):
        wait_before_openrouter_request()
        last = requests_mod.post(url, headers=headers, json=json_payload, timeout=timeout)
        if last.status_code not in retryable:
            return last
        if attempt >= max_retries:
            return last
        wait_s = _retry_wait_seconds(last, attempt, base_backoff)
        log.warning(
            "OpenRouter HTTP %s (attempt %d/%d), retry in %.1fs",
            last.status_code,
            attempt + 1,
            max_retries + 1,
            wait_s,
        )
        time.sleep(wait_s)
    return last
