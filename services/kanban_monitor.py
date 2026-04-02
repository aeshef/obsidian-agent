from planning_bot.core.pdmsg import pdmsg
import json
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from planning_bot.core.config import KANBAN_FILE, LOGS_DIR, ACTION_LOGS_DIR, DONE_COLUMN
from planning_bot.services.kanban import KanbanBoard
from planning_bot.services.action_logger import ActionLogger


class KanbanMonitor:
    def __init__(self, state_file: Optional[Path] = None):
        # (comment)
        self.kanban_state_file = Path(state_file) if state_file is not None else (LOGS_DIR / "kanban_state.json")
        # (comment)
        self.monitor_state_file = LOGS_DIR / ".kanban_monitor_state.json"
        
        self.last_state_hash = None
        self.last_state: Dict = {}
        self.kanban = KanbanBoard()
        self.logger = ActionLogger(ACTION_LOGS_DIR)
        
        # (comment)
        self._load_monitor_state()
        # (comment)
        self._sync_kanban_state_json()
    
    def load_state_from_markdown(self) -> Dict:
        'Operation implementation.'
        if not KANBAN_FILE.exists():
            return {}
        
        try:
            with open(KANBAN_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # (comment)
            sections = list(re.finditer(r'^## (.+)$', content, re.MULTILINE))
            state = {}
            
            for i, section_match in enumerate(sections):
                section_name = section_match.group(1).strip()
                section_start = section_match.end()
                
                # (comment)
                if i + 1 < len(sections):
                    section_end = sections[i + 1].start()
                else:
                    # (comment)
                    settings_match = re.search(r'%% kanban:settings', content[section_start:])
                    section_end = section_start + settings_match.start() if settings_match else len(content)
                
                section_content = content[section_start:section_end]
                
                # (comment)
                for id_match in re.finditer(r'🆔 ID: ([a-f0-9-]+)', section_content):
                    task_id = id_match.group(1)
                    state[task_id] = section_name
            
            return state
        except Exception as e:
            print(pdmsg("auto_4298a2604a", e={e}))
            return {}
    
    def load_state(self) -> Dict:
        'Operation implementation.'
        state = self.load_state_from_markdown()
        self._save_kanban_state_json(state)
        return state
    
    def get_task_column_from_state(self, task_id: str) -> Optional[str]:
        'Operation implementation.'
        if not self.last_state:
            return None
        return self.last_state.get(task_id)
    
    def get_task_by_id(self, task_id: str) -> Optional[Dict]:
        'Operation implementation.'
        all_tasks = self.kanban.get_tasks(exclude_today=False)
        for task in all_tasks:
            if task.get("task_id") == task_id:
                return task
        return None
    
    def check_changes(self) -> list:
        'Operation implementation.'
        # (comment)
        # (comment)
        current_state = self.load_state_from_markdown()
        
        if not current_state:
            return []
        
        current_hash = hashlib.md5(json.dumps(current_state, sort_keys=True).encode()).hexdigest()
        
        # (comment)
        if current_hash == self.last_state_hash:
            return []
        
        changes = []
        
        # (comment)
        all_tasks = self.kanban.get_tasks(exclude_today=False)
        today = datetime.now().strftime("%Y-%m-%d")
        
        # (comment)
        for task_id, column in current_state.items():
            old_column = self.last_state.get(task_id)
            
            # (comment)
            if old_column != column:
                task = self.get_task_by_id(task_id)
                if task:
                    task_title = task.get("title", pdmsg("auto_29940f450a"))
                    
                    if old_column is None:
                        # (comment)
                        # (comment)
                        task_created_date = task.get("created_date", "")
                        if task_created_date == today:
                            # (comment)
                            history = self.logger.get_task_history(
                                task_title=task_title, task_id=task_id
                            )
                            if not history:
                                # (comment)
                                category = task.get("category", pdmsg("auto_aff66fb77a"))
                                priority = task.get("priority", pdmsg("auto_16916c0f4c"))
                                self.logger.log_task_created(
                                    task_title, category, priority, task_id=task_id
                                )
                    else:
                        # (comment)
                        changes.append({
                            "task_id": task_id,
                            "title": task_title,
                            "from": old_column,
                            "to": column,
                            "type": "move",
                            "category": task.get("category"),
                        })
        
        # (comment)
        # (comment)
        for task in all_tasks:
            task_title = task.get("title", "")
            task_id = task.get("task_id")
            task_created_date = task.get("created_date", "")
            
            # (comment)
            if not task_id and task_created_date == today:
                # (comment)
                history = self.logger.get_task_history(task_title=task_title)
                today_history = [h for h in history if h["timestamp"].startswith(today)]
                if not today_history:
                    # (comment)
                    category = task.get("category", pdmsg("auto_aff66fb77a"))
                    priority = task.get("priority", pdmsg("auto_16916c0f4c"))
                    self.logger.log_task_created(task_title, category, priority)
        
        # (comment)
        for task_id, old_column in self.last_state.items():
            if task_id not in current_state:
                task = self.get_task_by_id(task_id)
                if task:
                    task_title = task.get("title", pdmsg("auto_29940f450a"))
                    changes.append({
                        "task_id": task_id,
                        "title": task_title,
                        "from": old_column,
                        "to": None,
                        "type": "removed"
                    })
        
        # (comment)
        for change in changes:
            if change["type"] == "move":
                tid = change.get("task_id")
                category = change.get("category")
                if change["to"] == DONE_COLUMN:
                    self.logger.log_task_completed(change["title"], task_id=tid, category=category)
                else:
                    self.logger.log_task_moved(
                        change["title"],
                        change["from"],
                        change["to"],
                        task_id=tid,
                        category=category,
                    )
        
        # (comment)
        self.last_state = current_state.copy()
        self.last_state_hash = current_hash
        
        # (comment)
        self._save_monitor_state()
        self._save_kanban_state_json(current_state)
        
        return changes
    
    def _save_kanban_state_json(self, state: Dict):
        'Operation implementation.'
        try:
            self.kanban_state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.kanban_state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(pdmsg("auto_4c37031bbf", e={e}))

    def _load_monitor_state(self) -> None:
        'Operation implementation.'
        if not self.monitor_state_file.exists():
            self.last_state = {}
            self.last_state_hash = None
            return
        try:
            data = json.loads(self.monitor_state_file.read_text(encoding="utf-8"))
            self.last_state = data.get("last_state") or {}
            self.last_state_hash = data.get("last_hash")
            # (comment)
            if not self.last_state_hash and self.last_state:
                self.last_state_hash = hashlib.md5(json.dumps(self.last_state, sort_keys=True).encode()).hexdigest()
        except Exception as e:
            print(pdmsg("auto_17d924d3af", e={e}))
            self.last_state = {}
            self.last_state_hash = None

    def _save_monitor_state(self) -> None:
        'Operation implementation.'
        try:
            self.monitor_state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {"last_state": self.last_state, "last_hash": self.last_state_hash}
            self.monitor_state_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(pdmsg("auto_11df4c23e2", e={e}))

    def _sync_kanban_state_json(self) -> None:
        'Operation implementation.'
        st = self.load_state_from_markdown()
        if st:
            self._save_kanban_state_json(st)


def monitor_kanban_changes():
    'Operation implementation.'
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(pdmsg("auto_7de3d1332b", timestamp={timestamp}), flush=True)
    
    try:
        monitor = KanbanMonitor()
        changes = monitor.check_changes()
        
        if changes:
            print(pdmsg("auto_5fb8885df4", _p1=timestamp, _p3=len(changes)), flush=True)
            for change in changes:
                print(f"  - {change['title']}: {change.get('from')} → {change.get('to')}", flush=True)
        else:
            print(pdmsg("auto_5277544ed2", _p1=timestamp, _p3=len(monitor.last_state)), flush=True)
        
        return changes
    except Exception as e:
        print(pdmsg("auto_9dbd4636a9", timestamp={timestamp}, e={e}), flush=True)
        import traceback
        traceback.print_exc()
        return []


if __name__ == "__main__":
    # (comment)
    monitor_kanban_changes()