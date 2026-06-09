from planning_bot.core.pdmsg import pdmsg
import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from functools import lru_cache
from typing import Dict, List, Optional, Set, Tuple
from planning_bot.core.config import ACTION_LOGS_DIR, ACTION_LOG_PREFIX, DONE_COLUMN
from planning_bot.services.action_log_format import (
    content_for_parse,
    format_log_entry,
    gap_before_next_entry,
    needs_repair,
    repair_log_text,
)

_log = logging.getLogger(__name__)

_TASK_EVENT_TYPES = frozenset({"task_moved", "task_completed", "task_created"})
_LOG_ENTRY_RE = re.compile(
    pdmsg("auto_9158eed63e"),
    re.DOTALL,
)


def _read_log_file(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return content_for_parse(f.read())


@lru_cache(maxsize=1)
def _legacy_log_entry_re() -> re.Pattern[str]:
    """Regex for corrupted 2026-06 logs; pattern in planning.log_entry_legacy_regex (YAML)."""
    pat = pdmsg("log_entry_legacy_regex").strip()
    return re.compile(pat, re.DOTALL) if pat else re.compile(r"(?!)")


class ActionLogger:
    def __init__(self, logs_dir: Path = ACTION_LOGS_DIR):
        self.logs_dir = Path(logs_dir).resolve()
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        _log.debug(pdmsg("auto_913449b759"), self.logs_dir)

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
            for match in list(_LOG_ENTRY_RE.finditer(content)) + list(
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

    def query_task_events(
        self,
        *,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        hours: Optional[float] = None,
        calendar_day: Optional[date] = None,
        event_types: Optional[Set[str]] = None,
        task_id: Optional[str] = None,
        task_title: Optional[str] = None,
        limit: Optional[int] = None,
        safety_max: Optional[int] = None,
    ) -> Tuple[List[Dict], int]:
        'Operation implementation.'
        from shared.agent.platform_config import platform_int

        cap = safety_max if safety_max is not None else platform_int(
            "planning_action_log", "safety_max_events", default=10000
        )
        now = datetime.now()
        if calendar_day is not None:
            months = self._months_for_span(calendar_day, calendar_day)
            entries = self._load_task_events(months)
            entries = [e for e in entries if e["datetime"].date() == calendar_day]
        else:
            if hours is not None:
                cutoff = now - timedelta(hours=hours)
                start_d = cutoff.date()
                end_d = now.date()
            elif from_date or to_date:
                start_d = from_date or to_date or now.date()
                end_d = to_date or from_date or now.date()
                cutoff = datetime.combine(start_d, datetime.min.time())
            else:
                cutoff = None
                start_d = end_d = now.date()
            months = self._months_for_span(start_d, end_d)
            entries = self._load_task_events(months)
            if hours is not None and cutoff is not None:
                entries = [e for e in entries if e["datetime"] >= cutoff]
            elif from_date or to_date:
                if from_date:
                    entries = [e for e in entries if e["datetime"].date() >= from_date]
                if to_date:
                    entries = [e for e in entries if e["datetime"].date() <= to_date]

        if event_types:
            allowed = {t if t.startswith("task_") else f"task_{t}" for t in event_types}
            entries = [e for e in entries if e["type"] in allowed]
        tid = (task_id or "").strip()
        ttitle = (task_title or "").strip()
        if tid:
            entries = [e for e in entries if (e["data"].get("task_id") or "") == tid]
        elif ttitle:
            entries = [e for e in entries if (e["data"].get("title") or "") == ttitle]

        n_raw = len(entries)
        if limit is not None and limit > 0 and len(entries) > limit:
            entries = entries[-limit:]
        elif limit is None or limit <= 0:
            if len(entries) > cap:
                entries = entries[-cap:]

        # (comment)
        out = [
            {"timestamp": e["timestamp"], "type": e["type"], "data": e["data"]}
            for e in entries
        ]
        return out, n_raw

    def log_action(self, action_type: str, data: Dict):
        'Operation implementation.'
        today = datetime.now()
        log_file = self.logs_dir / f"{ACTION_LOG_PREFIX}{today.strftime('%Y-%m')}.md"

        # (comment)
        if not log_file.exists():
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(
                    pdmsg("auto_31eabb5043", _p1=today.strftime("%B %Y")) + "\n\n"
                )

        timestamp = today.strftime("%Y-%m-%d %H:%M:%S")
        # Do not use pdmsg for entry body: dmsg/pdmsg .strip() removes trailing newlines after
        # "---" in YAML (auto_ebf7357951), so the next append became "---## ...".
        entry = format_log_entry(timestamp, action_type, data)

        if log_file.exists() and log_file.stat().st_size > 0:
            raw = log_file.read_text(encoding="utf-8")
            if needs_repair(raw):
                fixed, n_fix = repair_log_text(raw)
                if n_fix:
                    log_file.write_text(fixed, encoding="utf-8")
                    _log.info("Repaired %s glued entries in %s before append", n_fix, log_file.name)

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(gap_before_next_entry(log_file))
            f.write(entry)

    def log_task_created(
        self,
        task_title: str,
        category: str,
        priority: str,
        task_id: Optional[str] = None,
    ):
        'Operation implementation.'
        # (comment)
        # (comment)
        if task_id:
            history = self.get_task_history(task_id=task_id)
            if any(h.get("type") == "task_created" for h in history):
                return
        payload = {"title": task_title, "category": category, "priority": priority}
        if task_id:
            payload["task_id"] = task_id
        self.log_action("task_created", payload)

    def log_task_completed(
        self,
        task_title: str,
        task_id: Optional[str] = None,
        category: Optional[str] = None,
    ):
        'Operation implementation.'
        # (comment)
        # (comment)
        if task_id:
            history = self.get_task_history(task_id=task_id)
            if any(h.get("type") == "task_completed" for h in history):
                return
        payload = {"title": task_title}
        if task_id:
            payload["task_id"] = task_id
        if category:
            payload["category"] = category
        self.log_action("task_completed", payload)

    def log_task_moved(
        self,
        task_title: str,
        from_column: str,
        to_column: str,
        task_id: Optional[str] = None,
        category: Optional[str] = None,
    ):
        'Operation implementation.'
        payload = {
            "title": task_title,
            "from": from_column,
            "to": to_column,
        }
        if task_id:
            payload["task_id"] = task_id
        if category:
            payload["category"] = category
        self.log_action("task_moved", payload)

    def count_completed_tasks_this_week(self) -> int:
        'Operation implementation.'
        return len(self.get_completed_this_week())

    def get_weekly_logs(self, limit: int = 50) -> str:
        'Operation implementation.'
        from datetime import timedelta
        import re
        
        today = datetime.now()
        days_since_monday = today.weekday()
        week_start = today - timedelta(days=days_since_monday)
        week_start_str = week_start.strftime("%Y-%m-%d")
        
        log_file = self.logs_dir / f"{ACTION_LOG_PREFIX}{today.strftime('%Y-%m')}.md"

        if not log_file.exists():
            return pdmsg("auto_bd48343e5a")

        content = _read_log_file(log_file)

        # (comment)
        entries = []
        # (comment)
        pattern = pdmsg("auto_9158eed63e")

        for match in re.finditer(pattern, content, re.DOTALL):
            timestamp_str = match.group(1)
            entry_date = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            
            # (comment)
            if entry_date >= week_start:
                action_type = match.group(2)
                try:
                    data = json.loads(match.group(3))
                    entries.append({
                        "timestamp": timestamp_str,
                        "type": action_type,
                        "data": data
                    })
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass
        
        # (comment)
        entries.sort(key=lambda x: x["timestamp"], reverse=True)
        entries = entries[:limit]
        
        if not entries:
            return pdmsg("auto_16086131c5")
        
        # (comment)
        result = pdmsg("auto_87e5fbbd3a", week_start_str={week_start_str})
        for entry in entries:
            result += f"- {entry['timestamp']}: {entry['type']}"
            if entry['type'] == 'task_moved':
                result += f" - \"{entry['data'].get('title', '')}\" ({entry['data'].get('from', '')} → {entry['data'].get('to', '')})"
            elif entry['type'] == 'task_completed':
                result += f" - \"{entry['data'].get('title', '')}\""
            elif entry['type'] == 'task_created':
                result += f" - \"{entry['data'].get('title', '')}\" [{entry['data'].get('category', '')}, {entry['data'].get('priority', '')}]"
            result += "\n"
        
        return result

    def get_logs_last_days(self, days: int = 7, limit: int = 50) -> str:
        'Operation implementation.'
        import re

        now = datetime.now()
        period_start = now - timedelta(days=max(1, days))
        period_start_str = period_start.strftime("%Y-%m-%d")

        # (comment)
        months_to_check = [now.strftime("%Y-%m")]
        prev_month = (now.replace(day=1) - timedelta(days=1))
        prev_month_str = prev_month.strftime("%Y-%m")
        if prev_month_str not in months_to_check:
            months_to_check.append(prev_month_str)

        entries = []
        pattern = pdmsg("auto_9158eed63e")
        for month_str in months_to_check:
            log_file = self.logs_dir / f"{ACTION_LOG_PREFIX}{month_str}.md"
            if not log_file.exists():
                continue
            content = _read_log_file(log_file)
            for match in re.finditer(pattern, content, re.DOTALL):
                timestamp_str = match.group(1)
                entry_date = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                if entry_date < period_start:
                    continue
                action_type = match.group(2)
                try:
                    data = json.loads(match.group(3))
                except json.JSONDecodeError:
                    continue
                entries.append({"timestamp": timestamp_str, "type": action_type, "data": data})

        entries.sort(key=lambda x: x["timestamp"], reverse=True)
        entries = entries[:limit]
        if not entries:
            return pdmsg("auto_a53c12baf5", _p1=max(1, days))

        result = pdmsg("auto_350cb8f834", _p1=max(1, days), _p3=period_start_str)
        for entry in entries:
            result += f"- {entry['timestamp']}: {entry['type']}"
            if entry['type'] == 'task_moved':
                result += f" - \"{entry['data'].get('title', '')}\" ({entry['data'].get('from', '')} → {entry['data'].get('to', '')})"
            elif entry['type'] == 'task_completed':
                result += f" - \"{entry['data'].get('title', '')}\""
            elif entry['type'] == 'task_created':
                result += f" - \"{entry['data'].get('title', '')}\" [{entry['data'].get('category', '')}, {entry['data'].get('priority', '')}]"
            result += "\n"
        return result

    def get_events_chain_for_calendar_day(self, day: date) -> str:
        'Operation implementation.'
        return self.get_recent_events_chain(
            hours=None,
            max_events=None,
            calendar_day=day,
        )

    def get_events_chain_for_date_range(
        self,
        from_date: date,
        to_date: date,
        *,
        limit: int = 0,
    ) -> str:
        """Task event chain for inclusive calendar-day range."""
        from shared.agent.platform_config import platform_int

        _SAFETY_MAX = platform_int(
            "planning_action_log", "safety_max_events", default=10000
        )
        max_events = limit if limit > 0 else 0
        entries, n_raw = self.query_task_events(
            from_date=from_date,
            to_date=to_date,
            limit=max_events,
            safety_max=_SAFETY_MAX,
        )
        truncated = n_raw > len(entries)
        if not entries:
            return pdmsg(
                "agent_action_log_range_empty",
                start=from_date.isoformat(),
                end=to_date.isoformat(),
            )
        lines: List[str] = [
            pdmsg("auto_6b600fff04"),
            pdmsg(
                "agent_action_log_chain_period",
                start=from_date.isoformat(),
                end=to_date.isoformat(),
                count=len(entries),
                raw=n_raw,
            ),
        ]
        if truncated:
            if max_events > 0:
                lines.append(pdmsg("auto_e8ccd17309", max_events=max_events))
            else:
                lines.append(pdmsg("auto_3284298d7e", _SAFETY_MAX=_SAFETY_MAX))
        lines.append("")
        for e in entries:
            ts = e["timestamp"]
            t = e["type"]
            d = e["data"]
            title = (d.get("title") or "?").replace("\n", " ")
            if t == "task_moved":
                lines.append(
                    f'{ts} | {t} | "{title}" | {d.get("from", "")} → {d.get("to", "")}'
                )
            elif t == "task_completed":
                lines.append(f'{ts} | {t} | "{title}"')
            elif t == "task_created":
                lines.append(
                    f'{ts} | {t} | "{title}" | {d.get("category", "")} / {d.get("priority", "")}'
                )
        lines.append("")
        lines.append(pdmsg("auto_6123f35713"))
        return "\n".join(lines)

    def get_recent_events_chain(
        self,
        hours: Optional[float] = None,
        max_events: Optional[int] = None,
        calendar_day: Optional[date] = None,
    ) -> str:
        'Operation implementation.'
        from shared.agent.platform_config import platform_float, platform_int

        _SAFETY_MAX = platform_int(
            "planning_action_log", "safety_max_events", default=10000
        )

        if calendar_day is not None:
            hours = 0.0
            max_events = max_events if max_events is not None else 0
        else:
            if hours is None:
                hours = platform_float(
                    "planning_action_log",
                    "chain_hours",
                    env="PLANNING_CHAT_LOG_CHAIN_HOURS",
                    default=48.0,
                )
            if max_events is None:
                max_events = platform_int(
                    "planning_action_log",
                    "chain_max_events",
                    env="PLANNING_CHAT_LOG_CHAIN_MAX_EVENTS",
                    default=0,
                )

        now = datetime.now()
        cutoff = now - timedelta(hours=hours) if calendar_day is None else None

        if calendar_day is not None:
            entries, n_raw = self.query_task_events(
                calendar_day=calendar_day,
                limit=max_events if max_events > 0 else 0,
                safety_max=_SAFETY_MAX,
            )
        else:
            entries, n_raw = self.query_task_events(
                hours=hours,
                limit=max_events if max_events > 0 else 0,
                safety_max=_SAFETY_MAX,
            )

        truncated = n_raw > len(entries)

        _log.debug(
            "get_recent_events_chain: window=%.1fh raw_events=%d after_cap=%d truncated=%s",
            hours,
            n_raw,
            len(entries),
            truncated,
        )

        if not entries:
            if calendar_day is not None:
                return (
                    pdmsg("auto_cee6069b3a", _p1=calendar_day.isoformat(), _p3=self.logs_dir)
                )
            return pdmsg(
                "history_hours_empty",
                hours=f"{hours:.0f}",
                logs_dir=self.logs_dir,
            )

        if calendar_day is not None:
            header = (
                pdmsg("auto_6b600fff04")
            )
            window_line = (
                pdmsg("auto_76473f45d3", _p1=calendar_day.isoformat(), _p3=len(entries), _p5=n_raw)
            )
        else:
            header = (
                pdmsg("auto_5a1c921e96")
            )
            window_line = pdmsg(
                "history_window_line",
                start=cutoff.strftime("%Y-%m-%d %H:%M"),
                end=now.strftime("%Y-%m-%d %H:%M"),
                hours=f"{hours:.0f}",
                count=len(entries),
                raw=n_raw,
            )

        lines: List[str] = [header, window_line]
        if truncated:
            if max_events > 0:
                lines.append(
                    pdmsg("auto_e8ccd17309", max_events={max_events})
                )
            else:
                lines.append(
                    pdmsg("auto_3284298d7e", _SAFETY_MAX={_SAFETY_MAX})
                )
        lines.append("")
        for e in entries:
            ts = e["timestamp"]
            t = e["type"]
            d = e["data"]
            title = (d.get("title") or "?").replace("\n", " ")
            if t == "task_moved":
                lines.append(
                    f"{ts} | {t} | \"{title}\" | {d.get('from', '')} → {d.get('to', '')}"
                )
            elif t == "task_completed":
                lines.append(f"{ts} | {t} | \"{title}\"")
            elif t == "task_created":
                lines.append(
                    f"{ts} | {t} | \"{title}\" | {d.get('category', '')} / {d.get('priority', '')}"
                )
        lines.append("")
        lines.append(
            pdmsg("auto_6123f35713")
        )
        return "\n".join(lines)

    def get_completed_this_week(self) -> List[Dict]:
        'Operation implementation.'
        from datetime import timedelta
        import re

        today = datetime.now()
        days_since_monday = today.weekday()
        week_start = today - timedelta(days=days_since_monday)

        raw = []
        months_to_check = [today.strftime("%Y-%m")]
        if today.day <= 7:
            prev_month = (today.replace(day=1) - timedelta(days=1))
            months_to_check.append(prev_month.strftime("%Y-%m"))

        pattern = pdmsg("auto_9158eed63e")

        for month_str in months_to_check:
            log_file = self.logs_dir / f"{ACTION_LOG_PREFIX}{month_str}.md"
            if not log_file.exists():
                continue
            content = _read_log_file(log_file)
            for match in re.finditer(pattern, content, re.DOTALL):
                timestamp_str = match.group(1)
                entry_date = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                if entry_date < week_start:
                    continue
                action_type = match.group(2).strip()
                try:
                    data = json.loads(match.group(3))
                except json.JSONDecodeError:
                    continue
                title = data.get("title") if isinstance(data, dict) else None
                if not title:
                    continue
                if action_type == "task_completed":
                    raw.append({
                        "task_id": data.get("task_id"),
                        "title": title,
                        "timestamp": timestamp_str,
                    })
                elif action_type == "task_moved" and data.get("to") == DONE_COLUMN:
                    raw.append({
                        "task_id": data.get("task_id"),
                        "title": title,
                        "timestamp": timestamp_str,
                    })

        # (comment)
        seen_id = set()
        seen_title = set()
        result = []
        for item in raw:
            key_id = item.get("task_id")
            key_title = item["title"]
            if key_id:
                if key_id in seen_id:
                    continue
                seen_id.add(key_id)
            else:
                if key_title in seen_title:
                    continue
                seen_title.add(key_title)
            result.append(item)
        return result

    def get_completed_last_days(self, days: int = 7) -> List[Dict]:
        'Operation implementation.'
        import re

        now = datetime.now()
        period_start = now - timedelta(days=max(1, days))

        raw = []
        months_to_check = [now.strftime("%Y-%m")]
        prev_month = (now.replace(day=1) - timedelta(days=1))
        prev_month_str = prev_month.strftime("%Y-%m")
        if prev_month_str not in months_to_check:
            months_to_check.append(prev_month_str)

        pattern = pdmsg("auto_9158eed63e")
        for month_str in months_to_check:
            log_file = self.logs_dir / f"{ACTION_LOG_PREFIX}{month_str}.md"
            if not log_file.exists():
                continue
            content = _read_log_file(log_file)
            for match in re.finditer(pattern, content, re.DOTALL):
                timestamp_str = match.group(1)
                entry_date = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                if entry_date < period_start:
                    continue
                action_type = match.group(2).strip()
                try:
                    data = json.loads(match.group(3))
                except json.JSONDecodeError:
                    continue
                title = data.get("title") if isinstance(data, dict) else None
                if not title:
                    continue
                if action_type == "task_completed":
                    raw.append({"task_id": data.get("task_id"), "title": title, "timestamp": timestamp_str})
                elif action_type == "task_moved" and data.get("to") == DONE_COLUMN:
                    raw.append({"task_id": data.get("task_id"), "title": title, "timestamp": timestamp_str})

        seen_id = set()
        seen_title = set()
        result = []
        for item in raw:
            key_id = item.get("task_id")
            key_title = item["title"]
            if key_id:
                if key_id in seen_id:
                    continue
                seen_id.add(key_id)
            else:
                if key_title in seen_title:
                    continue
                seen_title.add(key_title)
            result.append(item)
        return result

    def get_moved_events_this_week(self) -> List[Dict]:
        'Operation implementation.'
        from datetime import timedelta
        import re

        today = datetime.now()
        days_since_monday = today.weekday()
        week_start = today - timedelta(days=days_since_monday)

        result = []
        months_to_check = [today.strftime("%Y-%m")]
        if today.day <= 7:
            prev_month = (today.replace(day=1) - timedelta(days=1))
            months_to_check.append(prev_month.strftime("%Y-%m"))

        pattern = pdmsg("auto_9158eed63e")

        for month_str in months_to_check:
            log_file = self.logs_dir / f"{ACTION_LOG_PREFIX}{month_str}.md"
            if not log_file.exists():
                continue
            content = _read_log_file(log_file)
            for match in re.finditer(pattern, content, re.DOTALL):
                timestamp_str = match.group(1)
                entry_date = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                if entry_date < week_start:
                    continue
                action_type = match.group(2).strip()
                if action_type != "task_moved":
                    continue
                try:
                    data = json.loads(match.group(3))
                except json.JSONDecodeError:
                    continue
                result.append({
                    "timestamp": timestamp_str,
                    "task_id": data.get("task_id"),
                    "title": data.get("title") or "",
                    "from": data.get("from") or "",
                    "to": data.get("to") or "",
                })

        result.sort(key=lambda x: x["timestamp"])
        return result

    def get_moved_events_last_days(self, days: int = 7) -> List[Dict]:
        'Operation implementation.'
        import re

        now = datetime.now()
        period_start = now - timedelta(days=max(1, days))

        result = []
        months_to_check = [now.strftime("%Y-%m")]
        prev_month = (now.replace(day=1) - timedelta(days=1))
        prev_month_str = prev_month.strftime("%Y-%m")
        if prev_month_str not in months_to_check:
            months_to_check.append(prev_month_str)

        pattern = pdmsg("auto_9158eed63e")
        for month_str in months_to_check:
            log_file = self.logs_dir / f"{ACTION_LOG_PREFIX}{month_str}.md"
            if not log_file.exists():
                continue
            content = _read_log_file(log_file)
            for match in re.finditer(pattern, content, re.DOTALL):
                timestamp_str = match.group(1)
                entry_date = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                if entry_date < period_start:
                    continue
                action_type = match.group(2).strip()
                if action_type != "task_moved":
                    continue
                try:
                    data = json.loads(match.group(3))
                except json.JSONDecodeError:
                    continue
                result.append({
                    "timestamp": timestamp_str,
                    "task_id": data.get("task_id"),
                    "title": data.get("title") or "",
                    "from": data.get("from") or "",
                    "to": data.get("to") or "",
                })
        result.sort(key=lambda x: x["timestamp"])
        return result
    
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

    def get_task_history(
        self,
        task_title: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> List[Dict]:
        'Operation implementation.'
        if not task_id and not task_title:
            return []

        entries = self._load_task_events(self._all_log_months())
        history: List[Dict] = []
        for entry in entries:
            data = entry.get("data") or {}
            if task_id and data.get("task_id") == task_id:
                history.append(
                    {"timestamp": entry["timestamp"], "type": entry["type"], "data": data}
                )
            elif not task_id and task_title and data.get("title") == task_title:
                history.append(
                    {"timestamp": entry["timestamp"], "type": entry["type"], "data": data}
                )
        return history

    def get_task_status_on_date(
        self,
        date: "datetime | str",
        task_id: Optional[str] = None,
        task_title: Optional[str] = None,
    ) -> Optional[str]:
        'Operation implementation.'
        if not task_id and not task_title:
            return None
        from datetime import datetime as dt
        if isinstance(date, str):
            end_of_day = dt.strptime(date.strip() + " 23:59:59", "%Y-%m-%d %H:%M:%S")
        else:
            end_of_day = date.replace(hour=23, minute=59, second=59, microsecond=0)
        history = self.get_task_history(task_title=task_title, task_id=task_id)
        current_status = None
        for entry in history:
            ts = entry["timestamp"]
            try:
                event_time = dt.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if event_time > end_of_day:
                break
            if entry["type"] == "task_moved":
                current_status = entry["data"].get("to")
            elif entry["type"] == "task_completed":
                current_status = DONE_COLUMN
        return current_status
    
    def get_tasks_movement_history(self, tasks: List[Dict]) -> Dict[str, str]:
        'Operation implementation.'
        tasks_history = {}
        for task in tasks:
            task_id = task.get("task_id")
            task_title = task.get("title", "")
            if not task_title and not task_id:
                continue

            history = self.get_task_history(task_title=task_title or None, task_id=task_id)
            if not history:
                continue

            movement_chain = []
            for entry in history:
                if entry["type"] == "task_created":
                    movement_chain.append(pdmsg("auto_a86efaa406", _p1=entry['timestamp']))
                elif entry["type"] == "task_moved":
                    from_col = entry["data"].get("from", "")
                    to_col = entry["data"].get("to", "")
                    movement_chain.append(f"{entry['timestamp']}: {from_col} → {to_col}")
                elif entry["type"] == "task_completed":
                    movement_chain.append(pdmsg("auto_86fa86c8e2", _p1=entry['timestamp']))

            key = task_title or task_id or ""
            if movement_chain and key:
                tasks_history[key] = " → ".join(movement_chain)
        return tasks_history