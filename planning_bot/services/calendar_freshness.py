"""Freshness is source capture time, never just a successful script invocation."""
import json
from datetime import datetime, timezone
from pathlib import Path

from planning_bot.core.pdmsg import pdmsg
from planning_bot.services.calendar_bridge import config


def describe_calendar(path: Path) -> str:
    try:
        meta = json.loads(path.read_text()).get("meta", {})
        captured = meta.get("source_captured_at") or meta.get("txt_last_parsed")
        if not captured:
            return pdmsg("calendar_freshness_unknown")
        ts = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            import os
            from zoneinfo import ZoneInfo
            ts = ts.replace(tzinfo=ZoneInfo(os.environ.get("CALENDAR_TZ") or os.environ.get("TIMEZONE") or "UTC"))
        stale = (datetime.now(timezone.utc) - ts).total_seconds() > config()["stale_seconds"]
        return pdmsg("calendar_freshness_stale" if stale else "calendar_freshness_ok",
                     captured=captured, start=meta.get("coverage_start", "?"), end=meta.get("coverage_end", "?"))
    except (OSError, ValueError, TypeError):
        return pdmsg("calendar_freshness_unknown")
