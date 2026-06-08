from planning_bot.core.pdmsg import pdmsg
import re
from typing import List, Optional
from datetime import datetime
from planning_bot.core.config import GOALS_FILE, GOALS_CONTEXT_FILE


def current_quarter() -> str:
    month = datetime.now().month
    if month <= 3:
        return "Q1"
    if month <= 6:
        return "Q2"
    if month <= 9:
        return "Q3"
    return "Q4"


_FOCUS_TAG_RE = re.compile(r"#(?:фокус|focus)/[^\s#]+")
_GOAL_TAG_RE = re.compile(r"#(?:цель|goal)/[^\s#]+")
_PRIORITY_TAG_RE = re.compile(r"#(?:приоритет|priority)/[^\s#]+")
_DEADLINE_TAG_RE = re.compile(r"#(?:дедлайн|deadline)/[^\s#]+")


def _strip_goal_tags(goal_text: str, *, include_focus: bool = True) -> str:
    name = _GOAL_TAG_RE.sub("", goal_text)
    name = _PRIORITY_TAG_RE.sub("", name)
    if include_focus:
        name = _FOCUS_TAG_RE.sub("", name)
    name = _DEADLINE_TAG_RE.sub("", name)
    return name.strip()


def _has_focus_quarter(goal_text: str, quarter: str) -> bool:
    return bool(re.search(rf"#(?:фокус|focus)/{quarter}\b", goal_text))


class GoalsManager:
    def __init__(self):
        self.goals_file = GOALS_FILE
        self.goals_context_file = GOALS_CONTEXT_FILE

    def get_goals_context(self) -> Optional[str]:
        'Operation implementation.'
        if not self.goals_context_file.exists():
            return None

        try:
            with open(self.goals_context_file, 'r', encoding='utf-8') as f:
                content = f.read()
                return content
        except OSError:
            return None

    def get_goals_context_what_to_do_only(self) -> Optional[str]:
        'Operation implementation.'
        if not self.goals_context_file.exists():
            return None
        try:
            with open(self.goals_context_file, "r", encoding="utf-8") as f:
                full = f.read()
        except OSError:
            return None
        pattern = re.compile(
            pdmsg("auto_5a2b075f4b"),
            re.DOTALL,
        )
        blocks = [m.group(1).strip() for m in pattern.finditer(full) if m.group(1).strip()]
        if not blocks:
            return None
        return "\n\n---\n\n".join(blocks)

    def _iter_goal_lines(self, content: str):
        goal_pattern = r'- \[([ x])\] (.+?)(?=\n- \[|\n##|$)'
        yield from re.finditer(goal_pattern, content, re.DOTALL)

    def get_goals(self) -> List[str]:
        'Operation implementation.'
        if not self.goals_file.exists():
            return []

        with open(self.goals_file, 'r', encoding='utf-8') as f:
            content = f.read()

        goals = []
        for match in self._iter_goal_lines(content):
            is_completed = match.group(1) == 'x'
            goal_text = match.group(2).strip()
            goal_name = _strip_goal_tags(goal_text, include_focus=True)
            if not is_completed and goal_name:
                goals.append(goal_name)
        return goals

    def get_quarterly_focus(self) -> List[str]:
        """Active goals tagged #фокус/Qn for the current calendar quarter (from goals file)."""
        if not self.goals_file.exists():
            return []

        quarter = current_quarter()

        with open(self.goals_file, 'r', encoding='utf-8') as f:
            content = f.read()

        goals = []
        for match in self._iter_goal_lines(content):
            is_completed = match.group(1) == 'x'
            goal_text = match.group(2).strip()
            if not _has_focus_quarter(goal_text, quarter):
                continue
            goal_name = _strip_goal_tags(goal_text, include_focus=True)
            if not is_completed and goal_name:
                goals.append(goal_name)
        return goals
