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


def get_task_id_from_text(task_text: str) -> Optional[str]:
    'Operation implementation.'
    # (comment)
    id_match = re.search(r'🆔 ID: ([a-f0-9-]+)', task_text)
    if id_match:
        return id_match.group(1)
    
    # (comment)
    # (comment)
    date_match = re.search(pdmsg("auto_a84ca0473b"), task_text)
    category_match = re.search(pdmsg("auto_8d7e383ebe"), task_text)
    priority_match = re.search(pdmsg("auto_a1fb4d656a"), task_text)
    
    # (comment)
    task_name = re.sub(pdmsg("auto_8f87b9acbe"), '', task_text).strip()
    task_name = re.sub(pdmsg("auto_3a199272bb"), '', task_name).strip()
    task_name = re.sub(pdmsg("auto_259951b2bb"), '', task_name).strip()
    task_name = re.sub(pdmsg("auto_9943c12ad5"), '', task_name).strip()
    task_name = re.sub(r'\s*🆔 ID:.*', '', task_name).strip()
    normalized_task_name = task_name.replace('\\$', '$').replace('\\\\', '\\')
    
    # (comment)
    hash_parts = []
    if date_match:
        hash_parts.append(date_match.group(1))
    if category_match:
        hash_parts.append(category_match.group(1))
    if priority_match:
        hash_parts.append(priority_match.group(1))
    # (comment)
    hash_parts.append(normalized_task_name[:50])
    
    if hash_parts:
        hash_str = '|'.join(hash_parts)
        # (comment)
        return hashlib.md5(hash_str.encode('utf-8')).hexdigest()[:8]
    
    return None


def get_kanban_state() -> Dict[str, str]:
    'Operation implementation.'
    if not KANBAN_FILE.exists():
        return {}
    
    with open(KANBAN_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    state = {}
    
    # (comment)
    section_pattern = r'## ([^\n]+)\n\n(.*?)(?=\n## |\n%%|$)'
    
    for match in re.finditer(section_pattern, content, re.DOTALL):
        column_name = match.group(1).strip()
        if not column_name:
            continue
        section_content = match.group(2).strip()
        
        # (comment)
        task_pattern = r'- \[[ x]\]\s+(.+?)(?=\n- \[|$)'
        task_matches = re.finditer(task_pattern, section_content, re.DOTALL)
        
        for task_match in task_matches:
            task_text = task_match.group(1).strip()
            
            # (comment)
            task_id = get_task_id_from_text(task_text)
            
            if task_id:
                state[task_id] = column_name
    
    return state


def _trim_task_text_to_item(text: str) -> str:
    'Operation implementation.'
    for sep in ('\n## ', '\n%%'):
        if sep in text:
            text = text.split(sep)[0]
    return text.strip()


def get_task_title_by_id(task_id: str, kanban_content: str) -> Optional[str]:
    'Operation implementation.'
    # (comment)
    task_pattern = r'- \[[ x]\]\s+(.+?)(?=\n- \[|\n## |\n%%|$)'
    for match in re.finditer(task_pattern, kanban_content, re.DOTALL):
        task_text = _trim_task_text_to_item(match.group(1).strip())
        found_id = get_task_id_from_text(task_text)
        if found_id == task_id:
            # (comment)
            task_name = re.sub(pdmsg("auto_8f87b9acbe"), '', task_text).strip()
            task_name = re.sub(pdmsg("auto_3a199272bb"), '', task_name).strip()
            task_name = re.sub(pdmsg("auto_259951b2bb"), '', task_name).strip()
            task_name = re.sub(pdmsg("auto_9943c12ad5"), '', task_name).strip()
            task_name = re.sub(r'\s*🆔 ID:.*', '', task_name).strip()
            task_name = _trim_task_text_to_item(task_name)
            normalized_task_name = task_name.replace('\\$', '$').replace('\\\\', '\\')
            # (comment)
            normalized_task_name = re.sub(r'\s+', ' ', normalized_task_name).strip()
            return normalized_task_name
    return None


def get_task_category_from_text(task_text: str) -> Optional[str]:
    'Operation implementation.'
    m = re.search(pdmsg("auto_8d7e383ebe"), task_text)
    return m.group(1) if m else None


def get_task_category_by_id(task_id: str, kanban_content: str) -> Optional[str]:
    'Operation implementation.'
    task_pattern = r'- \[[ x]\]\s+(.+?)(?=\n- \[|\n## |\n%%|$)'
    for match in re.finditer(task_pattern, kanban_content, re.DOTALL):
        task_text = _trim_task_text_to_item(match.group(1).strip())
        if get_task_id_from_text(task_text) == task_id:
            return get_task_category_from_text(task_text)
    return None


def log_task_movements(logger: 'ActionLogger', previous_state: Dict[str, str], current_state: Dict[str, str]):
    'Operation implementation.'
    # (comment)
    if not KANBAN_FILE.exists():
        return
    
    with open(KANBAN_FILE, 'r', encoding='utf-8') as f:
        kanban_content = f.read()
    
    # (comment)
    for task_id, current_column in current_state.items():
        previous_column = previous_state.get(task_id)
        
        # (comment)
        if previous_column is None:
            continue
        
        # (comment)
        if previous_column != current_column:
            # (comment)
            task_title = get_task_title_by_id(task_id, kanban_content)
            if task_title:
                category = get_task_category_by_id(task_id, kanban_content)
                logger.log_task_moved(
                    task_title, previous_column, current_column, task_id=task_id, category=category
                )
                # (comment)
                if current_column == DONE_COLUMN:
                    logger.log_task_completed(task_title, task_id=task_id, category=category)

