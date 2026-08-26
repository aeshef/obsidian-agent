"""Action log file I/O and low-level event loading."""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from planning_bot.core.config import ACTION_LOG_PREFIX
from planning_bot.core.pdmsg import pdmsg
from planning_bot.services.action_log_format import content_for_parse

_log = logging.getLogger(__name__)

_TASK_EVENT_TYPES = frozenset(
    {"task_moved", "task_completed", "task_created", "task_deleted", "task_removed"}
)


@lru_cache(maxsize=1)
def _log_entry_re() -> re.Pattern[str]:
    return re.compile(pdmsg("auto_9158eed63e"), re.DOTALL)


def _read_log_file(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return content_for_parse(f.read())


@lru_cache(maxsize=1)
def _legacy_log_entry_re() -> re.Pattern[str]:
    """Regex for corrupted 2026-06 logs; pattern in planning.log_entry_legacy_regex (YAML)."""
    pat = pdmsg("log_entry_legacy_regex").strip()
    return re.compile(pat, re.DOTALL) if pat else re.compile(r"(?!)")


class ActionLogIO:
    def check_logs_dir_accessible(self) -> Tuple[bool, Optional[str]]:
        'Operation implementation.'
        if not self.logs_dir.exists():
            return False, (
                pdmsg("auto_806e09aed0")
            )
        if not self.logs_dir.is_dir():
            return False, (
                pdmsg("auto_678cec3c94")
            )
        try:
            list(self.logs_dir.iterdir())
        except OSError as e:
            return False, (
                pdmsg("auto_8e4c340dbc", e={e})
            )
        log_files = list(self.logs_dir.glob(f"{ACTION_LOG_PREFIX}*.md"))
        if not log_files:
            return False, (
                pdmsg("auto_c6fcbf7914")
            )
        return True, None

    @staticmethod
    def _months_for_span(start: date, end: date) -> List[str]:
        months: List[str] = []
        cur = date(start.year, start.month, 1)
        end_m = date(end.year, end.month, 1)
        while cur <= end_m:
            key = cur.strftime("%Y-%m")
            if key not in months:
                months.append(key)
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)
        return months

    def _load_task_events(self, months: List[str]) -> List[Dict]:
        entries: List[Dict] = []
        for month_str in months:
            log_file = self.logs_dir / f"{ACTION_LOG_PREFIX}{month_str}.md"
            if not log_file.exists():
                continue
            content = _read_log_file(log_file)
            for match in list(_log_entry_re().finditer(content)) + list(
                _legacy_log_entry_re().finditer(content)
            ):
                timestamp_str = match.group(1)
                try:
                    entry_dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                action_type = match.group(2).strip()
                if action_type not in _TASK_EVENT_TYPES:
                    continue
                try:
                    data = json.loads(match.group(3))
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                entries.append(
                    {
                        "timestamp": timestamp_str,
                        "datetime": entry_dt,
                        "type": action_type,
                        "data": data,
                    }
                )
        entries.sort(key=lambda x: x["timestamp"])
        return entries

    def _all_log_months(self) -> List[str]:
        from shared.agent.platform_config import platform_int

        months: List[str] = []
        prefix = ACTION_LOG_PREFIX
        for path in sorted(self.logs_dir.glob(f"{prefix}*.md")):
            suffix = path.name[len(prefix) :]
            if suffix.endswith(".md"):
                month = suffix[:-3]
                if len(month) == 7 and month[4] == "-":
                    months.append(month)
        months = sorted(set(months))
        cap = platform_int("planning_action_log", "task_history_months_max", default=0)
        if cap > 0:
            months = months[-cap:]
        return months

