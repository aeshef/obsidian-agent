"""Action log aggregates: completions, moves, task history."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from planning_bot.core.config import ACTION_LOG_PREFIX, DONE_COLUMN
from planning_bot.core.pdmsg import pdmsg

from .io import _read_log_file


class ActionLogAggregates:
    def count_completed_tasks_this_week(self) -> int:
        'Operation implementation.'
        return len(self.get_completed_this_week())

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
