"""Action log append / typed write helpers."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional

from planning_bot.core.config import ACTION_LOG_PREFIX
from planning_bot.core.pdmsg import pdmsg
from planning_bot.services.action_log_format import (
    format_log_entry,
    gap_before_next_entry,
    needs_repair,
    repair_log_text,
)

_log = logging.getLogger(__name__)


class ActionLogWrite:
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

    def log_task_deleted(
        self,
        task_title: str,
        task_id: Optional[str] = None,
        *,
        category: Optional[str] = None,
        from_column: Optional[str] = None,
        source: str = "explicit",
    ):
        """Intentional delete (bot/agent). Never auto-restore these."""
        if task_id:
            history = self.get_task_history(task_id=task_id)
            if any(h.get("type") == "task_deleted" for h in history):
                return
        payload: Dict = {"title": task_title, "source": source or "explicit"}
        if task_id:
            payload["task_id"] = task_id
        if category:
            payload["category"] = category
        if from_column:
            payload["from"] = from_column
        self.log_action("task_deleted", payload)

    def log_task_removed(
        self,
        task_title: str,
        task_id: Optional[str] = None,
        *,
        from_column: Optional[str] = None,
        source: str = "monitor",
    ):
        """Passive observation: task disappeared from the board (may be sync wipe).

        Not the same as task_deleted — restore may still treat these as orphans.
        """
        payload: Dict = {"title": task_title, "source": source or "monitor"}
        if task_id:
            payload["task_id"] = task_id
        if from_column:
            payload["from"] = from_column
        self.log_action("task_removed", payload)

