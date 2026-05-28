from planning_bot.core.pdmsg import pdmsg, pdmsg_nl
from shared.telegram_utils import strip_telegram_markdown
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from planning_bot.services.goals_mapper import GoalsMapper
from planning_bot.services.kanban import KanbanBoard
from planning_bot.core.config import KANBAN_FILE, DONE_COLUMN, IN_WORK_COLUMN, BACKLOG_COLUMN, GOALS_YEAR


class GoalsAnalyzer:
    def __init__(self):
        self.mapper = GoalsMapper()
        self.kanban = KanbanBoard()
    
    def get_goal_progress(self, goal_id: str) -> Dict:
        'Operation implementation.'
        goal = self.mapper.goals.get(goal_id)
        if not goal:
            return {}
        
        # (comment)
        task_ids = self.mapper.get_tasks_for_goal(goal_id)
        
        # (comment)
        self.kanban.load()
        all_tasks = self.kanban.get_tasks(exclude_today=False)
        task_dict = {t.get("task_id"): t for t in all_tasks if t.get("task_id")}
        
        # (comment)
        related_tasks = [task_dict[tid] for tid in task_ids if tid in task_dict]
        
        # (comment)
        total_tasks = len(related_tasks)
        # (comment)
        completed = len([t for t in related_tasks if t.get("is_completed") or t.get("column") == DONE_COLUMN])
        in_progress = len([t for t in related_tasks if t.get("column") == IN_WORK_COLUMN])
        backlog = len([t for t in related_tasks if (t.get("column") == BACKLOG_COLUMN or not t.get("column")) and not t.get("is_completed")])
        
        return {
            "goal": goal,
            "goal_id": goal_id,
            "total_tasks": total_tasks,
            "completed": completed,
            "in_progress": in_progress,
            "backlog": backlog,
            "tasks": related_tasks
        }
    
    def get_quarter_progress(self, quarter: str) -> Dict:
        'Operation implementation.'
        goals = self.mapper.get_goals_for_quarter(quarter)
        
        progress = {
            "quarter": quarter,
            "total_goals": len(goals),
            "goals": []
        }
        
        for goal_info in goals:
            goal_id = goal_info["id"]
            goal_progress = self.get_goal_progress(goal_id)
            progress["goals"].append(goal_progress)
        
        return progress
    
    def get_problematic_goals(self, quarter: Optional[str] = None) -> List[Dict]:
        'Operation implementation.'
        if quarter is None:
            quarter = self.mapper.get_current_quarter()
        
        goals = self.mapper.get_goals_for_quarter(quarter)
        problematic = []
        
        for goal_info in goals:
            goal_id = goal_info["id"]
            progress = self.get_goal_progress(goal_id)
            
            # (comment)
            # (comment)
            # (comment)
            # (comment)
            
            issues = []
            if progress["total_tasks"] == 0:
                issues.append("no_tasks")
            elif progress["in_progress"] == 0 and progress["backlog"] > 0:
                issues.append("no_in_progress")
            
            # (comment)
            recent_completed = [
                t for t in progress.get("tasks", [])
                if (t.get("column") == DONE_COLUMN or t.get("is_completed"))
                and t.get("created_date")
            ]
            if progress["total_tasks"] > 0 and len(recent_completed) == 0:
                issues.append("no_recent_progress")
            
            if issues:
                problematic.append({
                    "goal": goal_info,
                    "goal_id": goal_id,
                    "progress": progress,
                    "issues": issues
                })
        
        return problematic
    
    def format_progress_text(self, quarter: str) -> str:
        'Operation implementation.'
        progress = self.get_quarter_progress(quarter)
        
        text = pdmsg_nl("auto_3f6fe2ff62", quarter={quarter}, GOALS_YEAR={GOALS_YEAR})

        for goal_data in progress["goals"]:
            goal = goal_data["goal"]
            goal_id = goal_data["goal_id"]
            
            emoji = {
                pdmsg("auto_3520ab2a19"): "🔥",
                pdmsg("auto_16916c0f4c"): "🟡",
                pdmsg("auto_d821e337dd"): "⚪"
            }.get(goal.get("priority", ""), "⚪")
            
            title = strip_telegram_markdown(str(goal.get("text") or ""))
            text += f"{emoji} {title}\n"
            text += pdmsg_nl("auto_6f07b0b6d6", _p1=goal_data["total_tasks"])
            text += f"✅ {goal_data['completed']} | "
            text += f"🔄 {goal_data['in_progress']} | "
            text += f"📋 {goal_data['backlog']}\n\n"
        
        return text
    
    def format_alerts_text(self, quarter: Optional[str] = None) -> str:
        'Operation implementation.'
        problematic = self.get_problematic_goals(quarter)
        
        if not problematic:
            return pdmsg("auto_4ff2af9dec")
        
        text = pdmsg_nl("auto_00efa126bb")

        for item in problematic:
            goal = item["goal"]
            issues = item["issues"]
            
            emoji = {
                pdmsg("auto_3520ab2a19"): "🔥",
                pdmsg("auto_16916c0f4c"): "🟡",
                pdmsg("auto_d821e337dd"): "⚪"
            }.get(goal.get("priority", ""), "⚪")
            
            title = strip_telegram_markdown(str(goal.get("text") or ""))
            text += f"{emoji} {title}\n"

            if "no_tasks" in issues:
                text += pdmsg_nl("auto_f471ac35df")
            if "no_in_progress" in issues:
                text += pdmsg_nl("auto_e1ceb75da5")
            if "no_recent_progress" in issues:
                text += pdmsg_nl("auto_77245b49b2")
            text += "\n"
        
        return text
