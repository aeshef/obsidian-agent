"""Subjective daily signals — vault history under routines folder."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from planning_bot.services.daily_checkin_config import signals_config
from planning_bot.services.routines_lock import routines_transaction
from planning_bot.services.routines_manager import get_today_date
from shared.routines_paths import signals_config_path, signals_history_path
from shared.tz import get_tz
from shared.yaml_config import load_yaml


def ensure_signals_layout() -> None:
    from planning_bot.services.routines_layout import ensure_routines_layout

    ensure_routines_layout(scaffold_stats=False)


def effective_signals() -> list[dict[str, Any]]:
    base = list(signals_config())
    vault_path = signals_config_path()
    if vault_path.is_file():
        over = load_yaml(vault_path, default={})
        if isinstance(over, dict):
            raw = over.get("signals")
            if isinstance(raw, list) and raw:
                return [dict(x) for x in raw if isinstance(x, dict) and x.get("id")]
    return base


def has_signals_for_date(date_str: str) -> bool:
    path = signals_history_path()
    if not path.is_file():
        return False
    content = path.read_text(encoding="utf-8")
    return f"## {date_str}" in content and "signals:" in content


def _human_summary(values: dict[str, Any]) -> str:
    from planning_bot.app.ui import pmsg

    parts: list[str] = []
    for sig in effective_signals():
        sid = str(sig.get("id", ""))
        if sid not in values:
            continue
        val = values[sid]
        parts.append(pmsg("checkin_signal_summary_line", signal_id=sid, value=val))
    return " · ".join(parts)


def append_signals_entry(values: dict[str, Any], *, date_str: str | None = None) -> None:
    path = signals_history_path()
    ensure_signals_layout()
    day = date_str or get_today_date()
    tz = get_tz()
    captured = datetime.now(timezone.utc).astimezone(tz).isoformat(timespec="seconds")
    tz_name = str(getattr(tz, "zone", tz))
    yaml_block = (
        f"date: {day}\n"
        f"captured_at: {captured}\n"
        f"source: telegram_checkin\n"
        f"timezone: {tz_name}\n"
        f"signals:\n"
    )
    for key, val in sorted(values.items()):
        yaml_block += f"  {key}: {val}\n"
    summary = _human_summary(values)
    entry = f"## {day}\n\n```yaml\n{yaml_block}```\n\n{summary}\n\n---\n\n"
    marker = f"## {day}"
    with routines_transaction(path):
        tail = ""
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            if marker in content:
                before, rest = content.split(marker, 1)
                if "\n## " in rest:
                    tail = "\n## " + rest.split("\n## ", 1)[1]
                content = before.rstrip() + "\n\n"
            else:
                content = content.rstrip() + "\n\n"
        else:
            from planning_bot.app.ui import pmsg

            content = pmsg("checkin_signals_history_header") + "\n\n"
        path.write_text(content + entry + tail, encoding="utf-8")
