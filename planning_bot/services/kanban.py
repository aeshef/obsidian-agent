from planning_bot.core.pdmsg import pdmsg
import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from planning_bot.core.config import (
    KANBAN_FILE, CATEGORY_ORDER, PRIORITY_ORDER, LOGS_DIR,
    KANBAN_COLUMNS, BACKLOG_COLUMN, IN_WORK_COLUMN, BLOCKED_COLUMN, DONE_COLUMN,
)
from planning_bot.services.kanban_utils import get_column_by_position
from planning_bot.services import kanban_parse as kp
from planning_bot.services.kanban_format import (
    normalize_category,
    normalize_priority,
    task_created_line,
    task_meta_line,
)


class KanbanBoard:
    def __init__(self, file_path: Path = KANBAN_FILE):
        self.file_path = file_path
        self.content = ""
        self.state_file = LOGS_DIR / "kanban_state.json"
        self._kanban_state: Dict = {}
        self.load()
        self.load_state()

    def load(self):
        'Operation implementation.'
        if not self.file_path.exists():
            raise FileNotFoundError(pdmsg("auto_f1a2415e4c", file_path={file_path}))
        
        with open(self.file_path, 'r', encoding='utf-8') as f:
            self.content = f.read()
    
    def load_state(self):
        'Operation implementation.'
        if not self.state_file.exists():
            self._kanban_state = {}
            return
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                self._kanban_state = json.load(f)
        except Exception:
            self._kanban_state = {}
    
    def get_task_column(self, task_id: str) -> Optional[str]:
        'Operation implementation.'
        return self._kanban_state.get(task_id)

    def save(self):
        'Operation implementation.'
        with open(self.file_path, 'w', encoding='utf-8') as f:
            f.write(self.content)

    def add_task_to_backlog(
        self,
        title: str,
        category: str,
        priority: str,
        created_date: Optional[str] = None
    ) -> str:
        'Operation implementation.'
        # (comment)
        self.load()
        self.load_state()

        if created_date is None:
            created_date = datetime.now().strftime("%Y-%m-%d")

        # (comment)
        task_id = str(uuid.uuid4())[:8]  # (comment)

        cat = normalize_category(category)
        pri = normalize_priority(priority)
        task_line = f"- [ ] {title}"
        task_meta = task_meta_line(cat, pri)
        task_date = task_created_line(created_date)
        task_id_line = f"\t🆔 ID: {task_id}"
        parts = [task_line]
        if task_meta.strip():
            parts.append(task_meta)
        if task_date.strip():
            parts.append(task_date)
        parts.append(task_id_line)
        new_task = "\n".join(parts)

        backlog_header = f"## {BACKLOG_COLUMN}"
        backlog_index = self.content.find(backlog_header)
        if backlog_index == -1:
            raise ValueError(pdmsg("auto_31a23d0c3d", BACKLOG_COLUMN={BACKLOG_COLUMN}))

        # (comment)
        after_header = backlog_index + len(backlog_header)
        next_line_break = self.content.find("\n", after_header)
        insert_position = next_line_break + 1

        # (comment)
        before = self.content[:insert_position]
        after = self.content[insert_position:]
        clean_after = after.lstrip("\n")
        self.content = before + "\n" + new_task + "\n" + clean_after

        self.save()
        return task_id

    def get_tasks(self, exclude_today: bool = True, exclude_blocked: bool = False) -> List[Dict]:
        'Operation implementation.'
        # (comment)
        self.load()
        self.load_state()
        tasks = []
        today = datetime.now().strftime("%Y-%m-%d")

        for column, block in kp.iter_tasks_with_columns(self.content):
            meta = kp.metadata_from_block(block)
            task_id = meta.get("task_id")
            if task_id:
                column = self.get_task_column(task_id) or column
            if exclude_blocked and column == BLOCKED_COLUMN:
                continue
            created_date = meta.get("created_date")
            if exclude_today and created_date == today:
                continue
            tasks.append({
                "title": meta.get("title") or "",
                "category": meta.get("category"),
                "priority": meta.get("priority"),
                "completed": meta.get("completed"),
                "created_date": created_date,
                "deadline": meta.get("deadline"),
                "task_id": task_id,
                "column": column,
                "raw_text": block,
            })

        return tasks

    def get_backlog_tasks(self, exclude_today: bool = False, exclude_blocked: bool = True) -> List[Dict]:
        'Operation implementation.'
        all_tasks = self.get_tasks(exclude_today=exclude_today, exclude_blocked=exclude_blocked)
        # (comment)
        backlog_tasks = [t for t in all_tasks if not t["completed"]]
        
        # (comment)
        def sort_key(task: Dict) -> tuple:
            priority_order = PRIORITY_ORDER.get(task.get("priority", pdmsg("auto_d821e337dd")), 99)
            category_order = CATEGORY_ORDER.get(task.get("category", ""), 99)
            return (priority_order, category_order)
        
        return sorted(backlog_tasks, key=sort_key)
    
    def get_active_tasks(self, exclude_today: bool = False, exclude_blocked: bool = True) -> List[Dict]:
        'Operation implementation.'
        all_tasks = self.get_tasks(exclude_today=exclude_today, exclude_blocked=exclude_blocked)
        active_columns = [BACKLOG_COLUMN, IN_WORK_COLUMN]
        active_tasks = [
            t for t in all_tasks 
            if not t["completed"] and (t.get("column") in active_columns or not t.get("column"))
        ]
        def sort_key(task: Dict) -> tuple:
            in_work = 0 if task.get("column") == IN_WORK_COLUMN else 1
            priority_order = PRIORITY_ORDER.get(task.get("priority", pdmsg("auto_d821e337dd")), 99)
            category_order = CATEGORY_ORDER.get(task.get("category", ""), 99)
            return (in_work, priority_order, category_order)
        
        return sorted(active_tasks, key=sort_key)

    def get_completed_tasks_this_week(self) -> List[Dict]:
        'Operation implementation.'
        return []

    def get_statistics(self, completed_this_week_from_logs: Optional[List[Dict]] = None) -> Dict:
        'Operation implementation.'
        all_tasks = self.get_tasks(exclude_today=False)
        # (comment)
        active_tasks = self.get_active_tasks(exclude_today=False)
        active_count = len(active_tasks)
        backlog_only = len([t for t in active_tasks if t.get("column") == BACKLOG_COLUMN])
        in_work_count = len([t for t in active_tasks if t.get("column") == IN_WORK_COLUMN])
        in_blocked = len([t for t in all_tasks if t.get("column") == BLOCKED_COLUMN])
        in_waiting_date = len([t for t in all_tasks if t.get("column") == KANBAN_COLUMNS[1]])
        in_postponed = len([t for t in all_tasks if t.get("column") == KANBAN_COLUMNS[2]])

        def _norm_title(s: str) -> str:
            'Operation implementation.'
            if not s:
                return ""
            s = re.sub(pdmsg("auto_62d2694709"), "", s)
            s = re.sub(pdmsg("auto_50fdb61cba"), "", s)
            s = re.sub(pdmsg("auto_912c5ee296"), "", s)
            s = re.sub(pdmsg("auto_1134e4c855"), "", s)
            s = re.sub(r"🆔 ID: [a-f0-9-]+", "", s)
            return s.strip()

        # (comment)
        if completed_this_week_from_logs is not None:
            # (comment)
            seen = set()
            unique = []
            for item in reversed(completed_this_week_from_logs):
                seen_key = item.get("task_id") or _norm_title(item.get("title") or "")
                if not seen_key or seen_key in seen:
                    continue
                seen.add(seen_key)
                unique.append(item)
            # (comment)
            title_to_task = {_norm_title(t["title"]): t for t in all_tasks}
            completed_this_week = []
            for item in unique:
                t = title_to_task.get(_norm_title(item.get("title") or ""))
                completed_this_week.append({
                    "title": item["title"],
                    "category": t.get("category") if t else None,
                    "priority": t.get("priority") if t else None,
                })
        else:
            completed_this_week = [t for t in all_tasks if t["completed"]]

        by_category = {}
        for task in completed_this_week:
            cat = (task.get("category") if isinstance(task, dict) else None) or pdmsg("auto_1945da1fe5")
            by_category[cat] = by_category.get(cat, 0) + 1

        by_priority = {
            pdmsg("auto_3520ab2a19"): sum(1 for t in completed_this_week if (t.get("priority") if isinstance(t, dict) else None) == pdmsg("auto_3520ab2a19")),
            pdmsg("auto_16916c0f4c"): sum(1 for t in completed_this_week if (t.get("priority") if isinstance(t, dict) else None) == pdmsg("auto_16916c0f4c")),
            pdmsg("auto_d821e337dd"): sum(1 for t in completed_this_week if (t.get("priority") if isinstance(t, dict) else None) == pdmsg("auto_d821e337dd")),
        }

        return {
            "completed": len(completed_this_week),
            "completed_this_week_list": completed_this_week,
            "by_category": by_category,
            "by_priority": by_priority,
            "backlog_size": active_count,
            "backlog_only": backlog_only,
            "in_work": in_work_count,
            "total_active": active_count,
            "in_blocked": in_blocked,
            "in_waiting_date": in_waiting_date,
            "in_postponed": in_postponed,
        }
    
    def get_tasks_with_deadlines(self, days_ahead: int = 7) -> List[Dict]:
        'Operation implementation.'
        from datetime import timedelta
        
        all_tasks = self.get_tasks(exclude_today=False, exclude_blocked=True)
        today = datetime.now().date()
        target_date = today + timedelta(days=days_ahead)
        
        tasks_with_deadlines = []
        for task in all_tasks:
            if task.get("completed"):
                continue
            
            deadline_str = task.get("deadline")
            if not deadline_str:
                continue
            
            try:
                deadline_date = datetime.strptime(deadline_str, "%Y-%m-%d").date()
                if today <= deadline_date <= target_date:
                    days_until = (deadline_date - today).days
                    task["days_until_deadline"] = days_until
                    tasks_with_deadlines.append(task)
            except ValueError:
                continue
        
        # (comment)
        tasks_with_deadlines.sort(key=lambda t: t.get("days_until_deadline", 999))
        return tasks_with_deadlines

    def get_tasks_with_missed_deadlines(self) -> List[Dict]:
        'Operation implementation.'
        from datetime import timedelta

        all_tasks = self.get_tasks(exclude_today=False, exclude_blocked=True)
        today = datetime.now().date()

        result = []
        for task in all_tasks:
            if task.get("completed"):
                continue
            deadline_str = task.get("deadline")
            if not deadline_str:
                continue
            try:
                deadline_date = datetime.strptime(deadline_str, "%Y-%m-%d").date()
                if deadline_date < today:
                    days_overdue = (today - deadline_date).days
                    task = dict(task)
                    task["days_overdue"] = days_overdue
                    result.append(task)
            except ValueError:
                continue

        result.sort(key=lambda t: t.get("days_overdue", 0), reverse=True)
        return result