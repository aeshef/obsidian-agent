"""Host navigation buttons — do not send to NLU / finance parser."""
from __future__ import annotations

from functools import lru_cache

from unified_bot.host import labels as host_labels


@lru_cache(maxsize=1)
def host_navigation_labels() -> frozenset[str]:
    return host_labels.mode_button_labels()


def clear_navigation_cache() -> None:
    host_navigation_labels.cache_clear()


def is_host_navigation(text: str | None) -> bool:
    return (text or "").strip() in host_navigation_labels()
