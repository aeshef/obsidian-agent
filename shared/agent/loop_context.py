"""Loop-side context helpers: clip LLM copies, refresh working set, pick join series."""
from __future__ import annotations

from typing import Any

from shared.agent.types import LOOP_TOOL_RESULTS_KEY
from shared.query.align_series import parse_day_values

WORKING_SET_HEAD = "Working set (recent context):"


def clip_text(text: str, max_chars: int) -> str:
    body = text or ""
    if not max_chars or len(body) <= max_chars:
        return body
    cut = max(1, max_chars - 1)
    return body[:cut].rstrip() + "…"


def clip_tool_result(full: str) -> tuple[str, dict]:
    """Return (text_for_llm, clip_stats). Full body stays elsewhere for verify/join."""
    from shared.agent.budget_caps import tool_result_max_chars

    raw = full or ""
    cap = tool_result_max_chars()
    clipped = clip_text(raw, cap)
    return clipped, {
        "raw_chars": len(raw),
        "llm_chars": len(clipped),
        "cap": int(cap or 0),
        "clipped": bool(cap and len(raw) > len(clipped)),
    }


def llm_tool_content(full: str) -> str:
    text, _stats = clip_tool_result(full)
    return text


def splice_working_set_block(system: str, block: str) -> str:
    sys = system or ""
    blob = (block or "").strip()
    if WORKING_SET_HEAD in sys:
        pre = sys.split(WORKING_SET_HEAD, 1)[0].rstrip()
        return f"{pre}\n\n{blob}" if blob else pre
    if not blob:
        return sys
    return f"{sys.rstrip()}\n\n{blob}" if sys.strip() else blob


def refresh_system_working_set(
    api_messages: list[dict[str, Any]],
    *,
    user_id: int,
    domain: str,
) -> None:
    if not api_messages:
        return
    from shared.memory.working_set import get_working_set

    ws = get_working_set(user_id, domain).format()
    first = api_messages[0]
    if (first or {}).get("role") != "system":
        return
    first["content"] = splice_working_set_block(str(first.get("content") or ""), ws)


def record_tool_result(ctx: Any, name: str, content: str) -> None:
    rows = ctx.extras.setdefault(LOOP_TOOL_RESULTS_KEY, [])
    if not isinstance(rows, list):
        rows = []
        ctx.extras[LOOP_TOOL_RESULTS_KEY] = rows
    rows.append({"name": str(name or ""), "content": content or ""})


def pick_join_series(
    results: list[dict[str, Any]] | None,
) -> tuple[str, str, str, str] | None:
    """Last two prior tool dumps that parse as day-value series (skip aggregators)."""
    skip = _skip_as_tally_source()
    scored: list[tuple[int, str, str]] = []
    for item in results or []:
        name = str((item or {}).get("name") or "")
        if name in skip:
            continue
        text = str((item or {}).get("content") or "")
        n = len(parse_day_values(text))
        if n:
            scored.append((n, name or "series", text))
    if len(scored) < 2:
        return None
    a, b = scored[-2], scored[-1]
    return a[2], b[2], a[1], b[1]


_DEFAULT_SKIP_AS_TALLY_SOURCE = frozenset({"align_day_series", "tally_event_shares"})


def _skip_as_tally_source() -> frozenset[str]:
    from shared.agent.platform_config import platform_value

    raw = platform_value("series_tools", "skip_as_tally_source", default=None)
    if isinstance(raw, list) and raw:
        return frozenset(str(x) for x in raw if str(x).strip())
    return _DEFAULT_SKIP_AS_TALLY_SOURCE


def pick_tally_source(
    results: list[dict[str, Any]] | None,
) -> tuple[str, str] | None:
    """Latest prior tool dump that parses as a timestamped category log."""
    from shared.query.tally_shares import parse_timestamped_categories

    skip = _skip_as_tally_source()
    last: tuple[str, str] | None = None
    for item in results or []:
        name = str((item or {}).get("name") or "")
        if name in skip:
            continue
        text = str((item or {}).get("content") or "")
        events, _col = parse_timestamped_categories(text)
        if len(events) >= 2:
            last = (name or "log", text)
    return last
