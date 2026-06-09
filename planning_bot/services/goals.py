from planning_bot.core.pdmsg import pdmsg
import re
from typing import List, Optional
from datetime import datetime
from planning_bot.core.config import GOALS_FILE, GOALS_CONTEXT_FILE, _kanban_schema


def current_quarter() -> str:
    month = datetime.now().month
    if month <= 3:
        return "Q1"
    if month <= 6:
        return "Q2"
    if month <= 9:
        return "Q3"
    return "Q4"


def _goal_re(key: str, fallback: str) -> re.Pattern[str]:
    pat = _kanban_schema().get(key) or fallback
    return re.compile(str(pat))


_FOCUS_TAG_RE = _goal_re("goal_strip_focus_regex", r"#(?:focus)/[^\s#]+")
_GOAL_TAG_RE = _goal_re("goal_strip_goal_regex", r"#(?:goal)/[^\s#]+")
_PRIORITY_TAG_RE = _goal_re("goal_strip_priority_regex", r"#(?:priority)/[^\s#]+")
_DEADLINE_TAG_RE = _goal_re("goal_strip_deadline_regex", r"#(?:deadline)/[^\s#]+")


def _strip_goal_tags(goal_text: str, *, include_focus: bool = True) -> str:
    name = _GOAL_TAG_RE.sub("", goal_text)
    name = _PRIORITY_TAG_RE.sub("", name)
    if include_focus:
        name = _FOCUS_TAG_RE.sub("", name)
    name = _DEADLINE_TAG_RE.sub("", name)
    return name.strip()


def _has_focus_quarter(goal_text: str, quarter: str) -> bool:
    tpl = str(
        _kanban_schema().get("goal_focus_quarter_regex_template")
        or r"#(?:focus)/{quarter}\b"
    )
    return bool(re.search(tpl.format(quarter=quarter), goal_text))


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
        """Active goals with focus tag for the current calendar quarter (from goals file)."""
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
