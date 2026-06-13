import json
from planning_bot.core.config import DONE_COLUMN
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from planning_bot.core.pdmsg import pdmsg
from planning_bot.services.action_log_format import content_for_parse
from typing import Callable, List
from functools import lru_cache

# (comment)


@lru_cache(maxsize=1)
def _log_entry_pattern() -> re.Pattern[str]:
    return re.compile(pdmsg("auto_9158eed63e"), re.DOTALL)


def parse_log_content(content: str) -> List[dict]:
    'Operation implementation.'
    content = content_for_parse(content)
    events = []
    pattern = _log_entry_pattern()
    for m in pattern.finditer(content):
        ts = m.group(1)
        try:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        try:
            data = json.loads(m.group(3))
        except Exception:
            continue
        events.append({
            "timestamp": ts,
            "dt": dt,
            "type": m.group(2).strip(),
            "data": data,
        })
    return events


def collect_events_from_logs(
    logs_dir: Path,
    *,
    log_glob: str = pdmsg("auto_4f9eed73b9"),
) -> List[dict]:
    'Operation implementation.'
    log_files = sorted(logs_dir.glob(log_glob))
    events = []
    for path in log_files:
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        events.extend(parse_log_content(content))
    events.sort(key=lambda e: e["dt"])
    return events


def is_completion_event(event: dict) -> bool:
    'Operation implementation.'
    if event.get("type") == "task_completed":
        return True
    if event.get("type") == "task_moved":
        data = event.get("data") or {}
        return data.get("to") == DONE_COLUMN
    return False


def filter_batch_completions(
    events: List[dict],
    minute_threshold: int = 5,
) -> List[dict]:
    'Operation implementation.'
    by_minute = defaultdict(list)
    for e in events:
        if not is_completion_event(e):
            continue
        key = (e["dt"].date(), e["dt"].hour, e["dt"].minute)
        by_minute[key].append(e)
    batch_minutes = {k for k, v in by_minute.items() if len(v) > minute_threshold}
    return [e for e in events if (e["dt"].date(), e["dt"].hour, e["dt"].minute) not in batch_minutes]


def first_completion_per_task(
    events: List[dict],
    key_fn: Callable[[dict], str],
) -> List[dict]:
    'Operation implementation.'
    seen = set()
    result = []
    for e in events:
        if not is_completion_event(e):
            continue
        key = key_fn(e)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(e)
    return result


def get_completion_events(
    events: List[dict],
    *,
    filter_batch: bool = True,
    batch_minute_threshold: int = 5,
    dedup_per_task: bool = True,
) -> List[dict]:
    'Operation implementation.'
    completion = [e for e in events if is_completion_event(e)]
    completion.sort(key=lambda e: e["dt"])
    if filter_batch:
        completion = filter_batch_completions(completion, minute_threshold=batch_minute_threshold)
    if dedup_per_task:
        def key_fn(e):
            d = e.get("data") or {}
            return d.get("task_id") or (d.get("title") or "").strip()
        completion = first_completion_per_task(completion, key_fn)
    return completion
