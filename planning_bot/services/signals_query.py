"""Read subjective daily signals history for agent tools."""
from __future__ import annotations

import re
from datetime import date, timedelta

from shared.routines_paths import signals_history_path
from shared.tz import now_in_tz

_DAY_RE = re.compile(r"^##\s+(20\d{2}-\d{2}-\d{2})\s*$", re.MULTILINE)
_YAML_RE = re.compile(r"```yaml\n(.*?)```", re.DOTALL)


def _parse_day_bounds(from_date: str, to_date: str, days: int) -> tuple[str, str]:
    today = now_in_tz().date()
    if from_date.strip() and to_date.strip():
        return from_date.strip()[:10], to_date.strip()[:10]
    if days and int(days) > 0:
        end = today
        start = end - timedelta(days=max(0, int(days) - 1))
        return start.isoformat(), end.isoformat()
    if from_date.strip():
        return from_date.strip()[:10], from_date.strip()[:10]
    # default: last 7 days
    end = today
    start = end - timedelta(days=6)
    return start.isoformat(), end.isoformat()


def format_daily_signals(
    *,
    from_date: str = "",
    to_date: str = "",
    days: int = 0,
    limit: int = 14,
) -> str:
    path = signals_history_path()
    if not path.is_file():
        return "(signals history missing)"
    start_s, end_s = _parse_day_bounds(from_date, to_date, days)
    try:
        start = date.fromisoformat(start_s)
        end = date.fromisoformat(end_s)
    except ValueError:
        return f"(invalid date range {start_s}..{end_s})"
    if end < start:
        start, end = end, start

    text = path.read_text(encoding="utf-8")
    matches = list(_DAY_RE.finditer(text))
    chunks: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        day = m.group(1)
        try:
            d = date.fromisoformat(day)
        except ValueError:
            continue
        if d < start or d > end:
            continue
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[m.start() : end_pos]
        ym = _YAML_RE.search(block)
        body = ym.group(1).strip() if ym else block.strip()
        # Drop trailing separator noise
        summary_lines = [
            ln.strip()
            for ln in block.splitlines()
            if ln.strip() and not ln.startswith("#") and "```" not in ln and ln.strip() != "---"
        ]
        human = ""
        for ln in summary_lines:
            if ln.startswith("date:") or ln.startswith("captured") or ln.startswith("source:") or ln.startswith("timezone:") or ln.startswith("signals:"):
                continue
            if ln.startswith("  "):
                continue
            human = ln
            break
        chunks.append((day, human or body[:240]))

    chunks.sort(key=lambda x: x[0], reverse=True)
    lim = max(1, min(int(limit or 14), 60))
    if not chunks:
        return f"(no signals in {start_s}..{end_s})"
    lines = [f"Daily signals {start_s}..{end_s} (showing {min(len(chunks), lim)}/{len(chunks)}):"]
    for day, body in chunks[:lim]:
        one = " ".join(body.split())
        lines.append(f"- {day}: {one[:300]}")
    return "\n".join(lines)
