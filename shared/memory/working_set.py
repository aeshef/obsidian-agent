"""Short-lived working set: entities inferred from recent turns for follow-ups.

Locale category tokens belong in ``routing.yaml`` (``host.working_set.category_patterns``).
"""
from __future__ import annotations

import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache

from shared.agent.types import AgentContext, AgentMessage

_ISO = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_MAX_ITEMS = 12
_lock = threading.Lock()
_store: dict[tuple[int, str], "WorkingSet"] = {}

# English-only fallbacks; locale lists live in routing.yaml.example.
_DEFAULT_CATEGORY_PATTERNS = (
    r"\bfood\b",
    r"\btransport\b",
    r"\bsubscription\w*\b",
    r"\bhealth\b",
)


@lru_cache(maxsize=1)
def _category_hint_re() -> re.Pattern[str]:
    from shared.agent.config import load_routing_config

    host = load_routing_config().get("host") or {}
    block = host.get("working_set") or {}
    raw = block.get("category_patterns") or list(_DEFAULT_CATEGORY_PATTERNS)
    if isinstance(raw, str):
        parts = [raw]
    else:
        parts = [str(p) for p in raw if str(p).strip()]
    if not parts:
        parts = list(_DEFAULT_CATEGORY_PATTERNS)
    return re.compile("|".join(f"(?:{p})" for p in parts), re.IGNORECASE)


def clear_working_set_pattern_cache() -> None:
    _category_hint_re.cache_clear()


@dataclass
class WorkingSet:
    categories: OrderedDict[str, None] = field(default_factory=OrderedDict)
    dates: OrderedDict[str, None] = field(default_factory=OrderedDict)
    notes: OrderedDict[str, None] = field(default_factory=OrderedDict)

    def touch_category(self, name: str) -> None:
        key = name.strip()
        if not key:
            return
        self.categories.pop(key, None)
        self.categories[key] = None
        while len(self.categories) > _MAX_ITEMS:
            self.categories.popitem(last=False)

    def touch_date(self, value: str) -> None:
        key = value.strip()
        if not key:
            return
        self.dates.pop(key, None)
        self.dates[key] = None
        while len(self.dates) > _MAX_ITEMS:
            self.dates.popitem(last=False)

    def format(self) -> str:
        parts: list[str] = []
        if self.categories:
            parts.append("categories: " + ", ".join(self.categories.keys()))
        if self.dates:
            parts.append("dates: " + ", ".join(self.dates.keys()))
        if self.notes:
            parts.append("notes: " + ", ".join(list(self.notes.keys())[-4:]))
        if not parts:
            return ""
        return "Working set (recent context):\n" + "\n".join(f"- {p}" for p in parts)


def _key(user_id: int, domain: str) -> tuple[int, str]:
    return (int(user_id), str(domain or "general"))


def get_working_set(user_id: int, domain: str) -> WorkingSet:
    with _lock:
        k = _key(user_id, domain)
        if k not in _store:
            _store[k] = WorkingSet()
        return _store[k]


def observe_text(user_id: int, domain: str, text: str) -> WorkingSet:
    ws = get_working_set(user_id, domain)
    t = text or ""
    for m in _ISO.finditer(t):
        ws.touch_date(m.group(1))
    for m in _category_hint_re().finditer(t):
        ws.touch_category(m.group(0))
    return ws


def clear_working_set(user_id: int | None = None) -> None:
    with _lock:
        if user_id is None:
            _store.clear()
            return
        dead = [k for k in _store if k[0] == int(user_id)]
        for k in dead:
            _store.pop(k, None)


class WorkingSetMemory:
    """Memory layer that injects the recent working set into the system prompt."""

    async def read(self, ctx: AgentContext) -> str:
        ws = get_working_set(ctx.user_id, ctx.domain)
        # Refresh from the current question so follow-ups see entities immediately.
        observe_text(ctx.user_id, ctx.domain, ctx.question or "")
        return ws.format()

    async def write(self, ctx: AgentContext, turn: AgentMessage) -> None:
        observe_text(ctx.user_id, ctx.domain, turn.content or "")


def working_set_layer() -> WorkingSetMemory:
    return WorkingSetMemory()
