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
    VAULT_PATH, KANBAN_FILE, GOALS_FILE,
    CATEGORY_ORDER, PRIORITY_ORDER, LOGS_DIR, ACTION_LOGS_DIR,
    KANBAN_COLUMNS, DONE_COLUMN, GOALS_YEAR,
)


def add_ids_to_tasks() -> bool:
    'Operation implementation.'
    if not KANBAN_FILE.exists():
        print(pdmsg("auto_11757cfc8b", KANBAN_FILE={KANBAN_FILE}), flush=True)
        return False
    
    with open(KANBAN_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # (comment)
    section_headers = list(re.finditer(r'^## (.+?)$', content, re.MULTILINE))
    
    if not section_headers:
        # (comment)
        print(pdmsg("auto_364715af2c"), flush=True)
        return False
    
    tasks_without_id = []
    import uuid
    
    # (comment)
    for i, header_match in enumerate(section_headers):
        section_name = header_match.group(1).strip()
        header_start = header_match.end()
        
        # (comment)
        if i + 1 < len(section_headers):
            section_end = section_headers[i + 1].start()
        else:
            settings_match = re.search(r'%% kanban:settings', content[header_start:])
            if settings_match:
                section_end = header_start + settings_match.start()
            else:
                section_end = len(content)
        
        section_content = content[header_start:section_end]
        
        # (comment)
        task_pattern = r'(- \[[ x]\]\s+.+?)(?=\n- \[|\n## |\n%%|$)'
        for match in re.finditer(task_pattern, section_content, re.DOTALL):
            task_text = match.group(1)
            # (comment)
            if not re.search(r'🆔 ID:', task_text):
                # (comment)
                abs_start = header_start + match.start()
                abs_end = header_start + match.end()
                tasks_without_id.append((abs_start, abs_end, task_text))
    
    if not tasks_without_id:
        print(pdmsg("auto_66bb7d7ca9"), flush=True)
        return True
    
    print(pdmsg("auto_336c8eadcd", _p1=len(tasks_without_id)), flush=True)
    
    # (comment)
    for start, end, task_text in reversed(tasks_without_id):
        # (comment)
        task_id = str(uuid.uuid4())[:8]
        # (comment)
        id_line = f"\t🆔 ID: {task_id}"
        task_lines = task_text.rstrip().split('\n')
        
        # (comment)
        date_line_index = None
        for idx, line in enumerate(task_lines):
            if pdmsg("auto_8a47bf6956") in line:
                date_line_index = idx
                break
        
        if date_line_index is not None:
            # (comment)
            new_task_lines = task_lines[:date_line_index + 1] + [id_line] + task_lines[date_line_index + 1:]
        else:
            # (comment)
            new_task_lines = task_lines + [id_line]
        
        new_task_text = '\n'.join(new_task_lines)
        
        # (comment)
        content = content[:start] + new_task_text + content[end:]
    
    # (comment)
    with open(KANBAN_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(pdmsg("auto_8a67c27e56", _p1=len(tasks_without_id)), flush=True)
    return True

