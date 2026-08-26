"""Action log query helpers (filtered event lists and text dumps)."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from planning_bot.core.config import ACTION_LOG_PREFIX
from planning_bot.core.pdmsg import pdmsg

from .io import _read_log_file


class ActionLogQuery:
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

