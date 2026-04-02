from planning_bot.core.pdmsg import pdmsg
import re
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from planning_bot.core.config import GOALS_FILE, QUARTERLY_FOCUS_FILE, GOALS_CONTEXT_FILE, GOALS_YEAR


class GoalsManager:
    def __init__(self):
        self.goals_file = GOALS_FILE
        self.quarterly_file = QUARTERLY_FOCUS_FILE
        self.goals_context_file = GOALS_CONTEXT_FILE

    def get_goals_context(self) -> Optional[str]:
        'Operation implementation.'
        if not self.goals_context_file.exists():
            return None
        
        try:
            with open(self.goals_context_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # (   )
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
        # ---    ###
        pattern = re.compile(
            pdmsg("auto_5a2b075f4b"),
            re.DOTALL,
        )
        blocks = [m.group(1).strip() for m in pattern.finditer(full) if m.group(1).strip()]
        if not blocks:
            return None
        return "\n\n---\n\n".join(blocks)

    def get_goals(self) -> List[str]:
        'Operation implementation.'
        if not self.goals_file.exists():
            return []

        with open(self.goals_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # (  - [ ])
        goals = []
        goal_pattern = r'- \[([ x])\] (.+?)(?=\n- \[|\n##|$)'
        matches = re.finditer(goal_pattern, content, re.DOTALL)

        for match in matches:
            is_completed = match.group(1) == 'x'
            goal_text = match.group(2).strip()
            
            # 
            goal_name = re.sub(pdmsg("auto_62d2694709"), '', goal_text)
            goal_name = re.sub(pdmsg("auto_50fdb61cba"), '', goal_name)
            goal_name = re.sub(pdmsg("auto_d18a00e42d"), '', goal_name)
            goal_name = goal_name.strip()

            if not is_completed and goal_name:
                goals.append(goal_name)

        return goals

    def get_quarterly_focus(self) -> List[str]:
        'Operation implementation.'
        if not self.quarterly_file.exists():
            return []

        with open(self.quarterly_file, 'r', encoding='utf-8') as f:
            content = f.read()

        month = datetime.now().month
        if month >= 1 and month <= 3:
            quarter_header = pdmsg("auto_561c20c167", GOALS_YEAR={GOALS_YEAR})
        elif month >= 4 and month <= 6:
            quarter_header = pdmsg("auto_494b0b3261", GOALS_YEAR={GOALS_YEAR})
        elif month >= 7 and month <= 9:
            quarter_header = pdmsg("auto_f902ff94b9", GOALS_YEAR={GOALS_YEAR})
        else:
            quarter_header = pdmsg("auto_e656cfaad5", GOALS_YEAR={GOALS_YEAR})

        # 
        quarter_index = content.find(quarter_header)
        if quarter_index == -1:
            return []

        # 
        next_quarter_index = content.find("## 🎯 Q", quarter_index + 1)
        next_deadline_index = content.find("## 📅", quarter_index + 1)
        next_done_index = content.find("## ✅", quarter_index + 1)

        end_index = len(content)
        if next_quarter_index != -1:
            end_index = min(end_index, next_quarter_index)
        if next_deadline_index != -1:
            end_index = min(end_index, next_deadline_index)
        if next_done_index != -1:
            end_index = min(end_index, next_done_index)

        quarter_content = content[quarter_index:end_index]

        # 
        goals = []
        task_pattern = r'- \[([ x])\] (.+?)(?=\n- \[|$)'
        matches = re.finditer(task_pattern, quarter_content, re.DOTALL)

        for match in matches:
            is_completed = match.group(1) == 'x'
            goal_text = match.group(2).strip()

            # 
            goal_name = re.sub(pdmsg("auto_62d2694709"), '', goal_text)
            goal_name = re.sub(pdmsg("auto_50fdb61cba"), '', goal_name)
            goal_name = re.sub(pdmsg("auto_efc3150d05"), '', goal_name)
            goal_name = goal_name.strip()

            if not is_completed and goal_name:
                goals.append(goal_name)

        return goals
