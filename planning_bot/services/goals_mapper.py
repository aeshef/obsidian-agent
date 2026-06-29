from planning_bot.core.pdmsg import pdmsg
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from planning_bot.core.config import VAULT_PATH, GOALS_FILE, MAPPING_FILE, GOALS_YEAR
from shared.goals.mapping_files import resolve_mapping_file, write_json_atomic

GOAL_CONTEXT_KEYS = {
    "context": "context",
    "контекст": "context",
    "meaning": "context",
    "смысл": "context",
    "include": "include",
    "includes": "include",
    "включать": "include",
    "считать": "include",
    "exclude": "exclude",
    "excludes": "exclude",
    "исключать": "exclude",
    "не считать": "exclude",
    "success": "success",
    "success criteria": "success",
    "критерий": "success",
    "успех": "success",
}

# (comment)
def get_goals_file():
    return GOALS_FILE

def get_mapping_file():
    return resolve_mapping_file(MAPPING_FILE)


class GoalsMapper:
    def __init__(self, mapping_file: Optional[Path] = None):
        self.goals: Dict[str, Dict] = {}  # goal_id -> goal_info
        self.mapping: Dict[str, List[str]] = {}  # task_id -> [goal_ids]
        self.task_titles: Dict[str, str] = {}  # task_id -> task_title
        self.vault_path = VAULT_PATH
        self.goals_file = GOALS_FILE
        self.mapping_file = mapping_file or get_mapping_file()
        self.load_goals()
        self.load_mapping()
    
    def load_goals(self):
        'Operation implementation.'
        self.goals = {}
        
        if self.goals_file.exists():
            content = self.goals_file.read_text(encoding='utf-8')
            self._parse_goals_from_content(content, self.goals_file)
    
    def _parse_goals_from_content(self, content: str, source_file: Path):
        'Operation implementation.'
        lines = content.split('\n')
        current_quarter = None
        in_fenced_code = False
        
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                in_fenced_code = not in_fenced_code
                continue
            if in_fenced_code:
                continue

            # (comment)
            quarter_match = re.search(r'Q([1-4])\s+' + str(GOALS_YEAR), line)
            if quarter_match:
                current_quarter = f"Q{quarter_match.group(1)}"
            
            # (comment)
            focus_match = re.search(pdmsg("auto_827cc0f384"), line)
            if focus_match:
                current_quarter = focus_match.group(1)
            
            # (comment)
            if line.strip().startswith('- [ ]'):
                goal_text = line.strip()[5:].strip()  # (comment)
                
                # (comment)
                tags = re.findall(r'#(\w+)/([^\s#]+)', goal_text)
                goal_id = None
                category = None
                priority = None
                quarter = current_quarter
                
                for tag_name, tag_value in tags:
                    if tag_name == pdmsg("auto_31a4ed5e78"):
                        category = tag_value
                    elif tag_name == pdmsg("auto_b1a77f5def"):
                        priority = tag_value
                    elif tag_name == pdmsg("auto_f1d3acb4fc"):
                        quarter = tag_value
                
                # (comment)
                goal_text_clean = re.sub(r'#\w+/[^\s#]+', '', goal_text).strip()
                
                # (comment)
                goal_id = self._generate_goal_id(goal_text_clean)
                
                if goal_id and goal_text_clean:
                    context_fields = self._parse_goal_context_fields(lines, i + 1)
                    self.goals[goal_id] = {
                        "text": goal_text_clean,
                        "category": category,
                        "priority": priority,
                        "quarter": quarter,
                        "source": source_file.name,
                        **context_fields,
                    }

    @staticmethod
    def _parse_goal_context_line(line: str) -> Optional[Tuple[str, str]]:
        s = line.strip()
        while s.startswith(">"):
            s = s[1:].strip()
        if s.startswith(("- ", "* ", "+ ")):
            s = s[2:].strip()
        while s.startswith(">"):
            s = s[1:].strip()
        match = re.match(r"([^:]+)::\s*(.*)$", s)
        if not match:
            return None
        raw_key = re.sub(r"\s+", " ", match.group(1).strip().lower())
        key = GOAL_CONTEXT_KEYS.get(raw_key)
        if not key:
            return None
        return key, match.group(2).strip()

    @classmethod
    def _parse_goal_context_fields(cls, lines: List[str], start_idx: int) -> Dict[str, str]:
        """Read Obsidian inline fields indented under a goal checkbox.

        Supported fields:
          context:: what the goal means
          include:: what should count as a direct step
          exclude:: what is adjacent but out of scope
          success:: what completion means
        """
        fields: Dict[str, str] = {}
        last_key: Optional[str] = None

        for line in lines[start_idx:]:
            if not line.strip():
                last_key = None
                continue
            if line == line.lstrip():
                break

            stripped = line.strip()
            if stripped.startswith("- ["):
                last_key = None
                continue

            parsed = cls._parse_goal_context_line(line)
            if parsed:
                key, value = parsed
                if value:
                    fields[key] = f"{fields[key]}; {value}" if fields.get(key) else value
                    last_key = key
                else:
                    last_key = key
                continue

            if last_key:
                continuation = stripped
                if continuation.startswith(("- ", "* ", "+ ")):
                    continuation = continuation[2:].strip()
                if continuation:
                    fields[last_key] = f"{fields[last_key]} {continuation}".strip()

        return fields
    
    def _generate_goal_id(self, text: str) -> str:
        'Operation implementation.'
        import hashlib
        # (comment)
        return hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
    
    def load_mapping(self):
        'Operation implementation.'
        if self.mapping_file.exists():
            try:
                with open(self.mapping_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # (comment)
                    if "task_to_goals" in data:
                        self.mapping = data.get("task_to_goals", {}).copy()
                    elif "readable_mapping" in data:
                        self.mapping = {
                            task_id: list(info.get("goal_ids", []))
                            for task_id, info in data.get("readable_mapping", {}).items()
                        }
                    else:
                        self.mapping = {}
                    
                    # (comment)
                    # (comment)
                    old_to_new = {}
                    for info in data.get("readable_mapping", {}).values():
                        for g in info.get("goals", []):
                            old_id, text = g.get("id"), g.get("text", "").strip()
                            if old_id and text:
                                new_id = self._generate_goal_id(text)
                                if new_id != old_id and new_id in self.goals:
                                    old_to_new[old_id] = new_id
                    
                    if old_to_new:
                        self.mapping = {
                            task_id: list({old_to_new.get(g, g) for g in goal_ids})
                            for task_id, goal_ids in self.mapping.items()
                        }
                        self.save_mapping()  # (comment)
                    
                    # (comment)
                    valid_goal_ids = set(self.goals.keys())
                    self.mapping = {
                        task_id: [gid for gid in goal_ids if gid in valid_goal_ids]
                        for task_id, goal_ids in self.mapping.items()
                    }
                    
                    # (comment)
                    self.task_titles = data.get("task_titles", {})
            except Exception as e:
                print(pdmsg("auto_2e4842c5ec", e={e}))
                self.mapping = {}
                self.task_titles = {}
        else:
            self.mapping = {}
            self.task_titles = {}
    
    def save_mapping(self, task_info: Optional[Dict] = None):
        'Operation implementation.'
        self.mapping_file.parent.mkdir(parents=True, exist_ok=True)
        
        # (comment)
        existing_data = {}
        if self.mapping_file.exists():
            try:
                with open(self.mapping_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except (OSError, json.JSONDecodeError, ValueError):
                pass
        
        # (comment)
        task_titles = self.task_titles.copy()  # (comment)
        if existing_data.get("task_titles"):
            task_titles.update(existing_data.get("task_titles", {}))
        if task_info:
            task_titles.update(task_info)
        
        # (comment)
        readable_mapping = {}
        for task_id, goal_ids in self.mapping.items():
            readable_mapping[task_id] = {
                "task_title": task_titles.get(task_id, pdmsg("auto_e693b7b2fb", task_id={task_id})),
                "goal_ids": goal_ids,
                "goals": [
                    {
                        "id": goal_id,
                        "text": self.goals.get(goal_id, {}).get("text", "Unknown"),
                        "quarter": self.goals.get(goal_id, {}).get("quarter", ""),
                        "priority": self.goals.get(goal_id, {}).get("priority", ""),
                        "category": self.goals.get(goal_id, {}).get("category", ""),
                        "context": self.goals.get(goal_id, {}).get("context", ""),
                        "include": self.goals.get(goal_id, {}).get("include", ""),
                        "exclude": self.goals.get(goal_id, {}).get("exclude", ""),
                        "success": self.goals.get(goal_id, {}).get("success", ""),
                    }
                    for goal_id in goal_ids
                ]
            }
        
        data = {
            "task_to_goals": self.mapping,  # (comment)
            "task_titles": task_titles,  # (comment)
            "readable_mapping": readable_mapping,  # (comment)
            "last_updated": datetime.now().isoformat()
        }
        write_json_atomic(self.mapping_file, data)
    
    def get_goals_for_quarter(self, quarter: str) -> List[Dict]:
        'Operation implementation.'
        return [
            {**goal, "id": goal_id}
            for goal_id, goal in self.goals.items()
            if goal.get("quarter") == quarter
        ]
    
    def get_goals_for_category(self, category: str) -> List[Dict]:
        'Operation implementation.'
        return [
            {**goal, "id": goal_id}
            for goal_id, goal in self.goals.items()
            if goal.get("category") == category
        ]
    
    def get_all_goals(self) -> List[Dict]:
        'Operation implementation.'
        return [
            {**goal, "id": goal_id}
            for goal_id, goal in self.goals.items()
        ]
    
    def get_tasks_for_goal(self, goal_id: str) -> List[str]:
        'Operation implementation.'
        return [
            task_id
            for task_id, goal_ids in self.mapping.items()
            if goal_id in goal_ids
        ]
    
    def add_task_mapping(self, task_id: str, goal_ids: List[str], task_title: Optional[str] = None):
        'Operation implementation.'
        # (comment)
        valid_goal_ids = [gid for gid in goal_ids if gid in self.goals]
        if valid_goal_ids:
            self.mapping[task_id] = valid_goal_ids
            task_info = {task_id: task_title} if task_title else None
            self.save_mapping(task_info=task_info)
    
    def remove_task_mapping(self, task_id: str):
        'Operation implementation.'
        if task_id in self.mapping:
            del self.mapping[task_id]
            self.save_mapping()

    def reconcile_mapping(
        self,
        *,
        known_task_ids: Optional[set] = None,
        persist: bool = True,
        remove_ghost_tasks: bool = False,
    ) -> Dict[str, int]:
        """Drop stale goal IDs (and optionally ghost tasks); persist if changed."""
        stats = {
            "orphan_goal_refs": 0,
            "ghost_tasks": 0,
            "empty_mappings_removed": 0,
        }
        valid_goal_ids = set(self.goals.keys())
        before = json.dumps(self.mapping, sort_keys=True)

        cleaned: Dict[str, List[str]] = {}
        for task_id, goal_ids in self.mapping.items():
            if remove_ghost_tasks and known_task_ids is not None and task_id not in known_task_ids:
                stats["ghost_tasks"] += 1
                continue
            filtered = [gid for gid in goal_ids if gid in valid_goal_ids]
            stats["orphan_goal_refs"] += len(goal_ids) - len(filtered)
            if filtered:
                cleaned[task_id] = filtered
            elif goal_ids:
                stats["empty_mappings_removed"] += 1
        self.mapping = cleaned

        if persist and json.dumps(self.mapping, sort_keys=True) != before:
            self.save_mapping()
        return stats
    
    def get_current_quarter(self) -> str:
        'Operation implementation.'
        month = datetime.now().month
        if month in [1, 2, 3]:
            return "Q1"
        elif month in [4, 5, 6]:
            return "Q2"
        elif month in [7, 8, 9]:
            return "Q3"
        else:
            return "Q4"
