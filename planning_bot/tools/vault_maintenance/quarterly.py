#!/usr/bin/env python3
from planning_bot.core.pdmsg import pdmsg
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_PARENT = PROJECT_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

# (comment)
from planning_bot.core.config import (
    VAULT_PATH, KANBAN_FILE, GOALS_FILE, QUARTERLY_FOCUS_FILE,
    CATEGORY_ORDER, PRIORITY_ORDER, LOGS_DIR, ACTION_LOGS_DIR,
    KANBAN_COLUMNS, DONE_COLUMN, GOALS_YEAR,
)


def sync_quarterly_focus() -> bool:
    'Operation implementation.'
    print(pdmsg("auto_f1cace2956"))
    
    if not GOALS_FILE.exists():
        print(pdmsg("auto_5f187c0b33", GOALS_FILE={GOALS_FILE}))
        return True
    
    with open(GOALS_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    goals_by_quarter: Dict[str, List[Tuple[str, bool]]] = {
        'Q1': [],
        'Q2': [],
        'Q3': [],
        'Q4': [],
        'deadlines': []
    }
    
    # (comment)
    task_pattern = r'- \[([ x])\] (.+?)(?=\n- \[|$)'
    tasks = re.findall(task_pattern, content, re.MULTILINE | re.DOTALL)
    
    for checked, task_text in tasks:
        is_completed = checked.strip() == 'x'
        
        # (comment)
        if pdmsg("auto_e01807b972") in task_text:
            goal_text = re.sub(pdmsg("auto_c0c9e46d0b"), '', task_text).strip()
            goals_by_quarter['deadlines'].append((goal_text, is_completed))
        
        # (comment)
        for quarter in ['Q1', 'Q2', 'Q3', 'Q4']:
            if pdmsg("auto_0a98cea7c8", quarter={quarter}) in task_text:
                goal_text = re.sub(pdmsg("auto_c3aaa0dd62"), '', task_text).strip()
                goals_by_quarter[quarter].append((goal_text, is_completed))
    
    if not QUARTERLY_FOCUS_FILE.exists():
        print(pdmsg("auto_d4b5061954", QUARTERLY_FOCUS_FILE={QUARTERLY_FOCUS_FILE}))
        return True
    
    with open(QUARTERLY_FOCUS_FILE, 'r', encoding='utf-8') as f:
        focus_content = f.read()
    
    # (comment)
    for quarter in ['Q1', 'Q2', 'Q3', 'Q4']:
        section_pattern = rf'## 🎯 {quarter} {GOALS_YEAR}.*?(?=## |```|%%|$)'
        section_match = re.search(section_pattern, focus_content, re.DOTALL)
        
        if section_match:
            # (comment)
            new_section = f"## 🎯 {quarter} {GOALS_YEAR} ("
            if quarter == 'Q1':
                new_section += pdmsg("auto_0702fd04ef")
            elif quarter == 'Q2':
                new_section += pdmsg("auto_8ea4816885")
            elif quarter == 'Q3':
                new_section += pdmsg("auto_248aa6015e")
            else:
                new_section += pdmsg("auto_56c162fb97")
            new_section += ")\n\n"
            
            # (comment)
            active_goals = [g for g, c in goals_by_quarter[quarter] if not c]
            for goal_text in active_goals:
                new_section += f"- [ ] {goal_text}\n"
            
            # (comment)
            if not active_goals:
                new_section += "- [ ] \n"
            
            new_section += "\n"
            
            # (comment)
            focus_content = focus_content[:section_match.start()] + new_section + focus_content[section_match.end():]
    
    # (comment)
    deadlines_pattern = pdmsg("auto_f884ed9745")
    deadlines_match = re.search(deadlines_pattern, focus_content, re.DOTALL)
    
    if deadlines_match:
        new_deadlines = pdmsg("auto_670acc4b48")
        for goal_text, is_completed in goals_by_quarter['deadlines']:
            if not is_completed:
                new_deadlines += f"- [ ] {goal_text}\n"
        
        if not any(not c for _, c in goals_by_quarter['deadlines']):
            new_deadlines += pdmsg("auto_822ebb7c86", GOALS_YEAR={GOALS_YEAR})
        
        focus_content = focus_content[:deadlines_match.start()] + new_deadlines + focus_content[deadlines_match.end():]
    
    # (comment)
    with open(QUARTERLY_FOCUS_FILE, 'w', encoding='utf-8') as f:
        f.write(focus_content)
    
    print(pdmsg("auto_97aef5c590"))
    
    # (comment)
    for quarter in ['Q1', 'Q2', 'Q3', 'Q4']:
        count = len([g for g, c in goals_by_quarter[quarter] if not c])
        print(pdmsg("auto_f9049c1ad5", quarter={quarter}, count={count}))
    
    return True

