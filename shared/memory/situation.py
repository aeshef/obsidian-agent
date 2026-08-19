"""Live situation block: today on calendar + kanban in-work. Fail open, cached."""
from __future__ import annotations

import logging
import time
from typing import Any

from shared.agent.types import AgentContext, AgentMessage
from shared.domain_messages import dmsg

log = logging.getLogger("shared.memory.situation")

_CACHE: dict[str, tuple[float, str]] = {}


def _situation_cfg() -> dict[str, Any]:
    from shared.memory.config import load_memory_config

    raw = load_memory_config().get("situation") or {}
    return raw if isinstance(raw, dict) else {}


def _int_cfg(key: str, default: int) -> int:
    try:
        return max(0, int(_situation_cfg().get(key, default)))
    except (TypeError, ValueError):
        return default


def _clip_lines(text: str, max_lines: int) -> str:
    body = (text or "").strip()
    if not body or max_lines <= 0:
        return ""
    lines = [ln.rstrip() for ln in body.splitlines() if ln.strip()]
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[:max_lines]) + "\n…"


def _calendar_block() -> str:
    max_lines = _int_cfg("calendar_max_lines", 8)
    if not max_lines:
        return ""
    try:
        from planning_bot.core.config import CALENDAR_JSON_FILE
        from planning_bot.services.calendar_service import (
            _today_in_calendar_tz,
            get_events_for_day_text,
        )

        if not CALENDAR_JSON_FILE.is_file():
            return ""
        raw = get_events_for_day_text(CALENDAR_JSON_FILE, _today_in_calendar_tz())
        clipped = _clip_lines(raw, max_lines)
        if not clipped:
            return ""
        return dmsg("memory_layers", "situation_calendar") + "\n" + clipped
    except Exception:
        log.debug("situation calendar failed", exc_info=True)
        return ""


def _wip_block() -> str:
    max_tasks = _int_cfg("wip_max_tasks", 8)
    if not max_tasks:
        return ""
    try:
        from planning_bot.core.config import IN_WORK_COLUMN
        from planning_bot.services.kanban import KanbanBoard

        if not IN_WORK_COLUMN:
            return ""
        board = KanbanBoard()
        tasks = [
            t
            for t in board.get_tasks(exclude_today=False, include_archive=False)
            if (t.get("column") or "") == IN_WORK_COLUMN
        ]
        titles: list[str] = []
        for t in tasks[:max_tasks]:
            title = str(t.get("title") or "").strip()
            if title:
                titles.append(f"- {title}")
        if not titles:
            return dmsg("memory_layers", "situation_wip_none")
        extra = f"\n…" if len(tasks) > max_tasks else ""
        return dmsg("memory_layers", "situation_wip") + "\n" + "\n".join(titles) + extra
    except Exception:
        log.debug("situation wip failed", exc_info=True)
        return ""


def collect_situation_text() -> str:
    parts = [p for p in (_calendar_block(), _wip_block()) if p]
    if not parts:
        return ""
    body = "\n\n".join(parts)
    cap = _int_cfg("max_chars", 1200)
    if cap and len(body) > cap:
        body = body[: cap - 1].rstrip() + "…"
    return dmsg("memory_layers", "situation_header") + "\n" + body


def _cache_key(user_id: int) -> str:
    return f"u:{user_id}"


class SituationMemory:
    """MemoryLayer: live HUD (calendar today, kanban in-work)."""

    async def read(self, ctx: AgentContext) -> str:
        ttl = _int_cfg("cache_sec", 60)
        key = _cache_key(ctx.user_id)
        now = time.monotonic()
        hit = _CACHE.get(key)
        if hit and ttl > 0 and now - hit[0] < ttl:
            return hit[1]
        text = collect_situation_text()
        _CACHE[key] = (now, text)
        return text

    async def write(self, ctx: AgentContext, turn: AgentMessage) -> None:
        pass
