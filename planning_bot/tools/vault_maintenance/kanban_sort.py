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


def sort_kanban_tasks(target_path: Optional[Path] = None) -> bool:
    'Operation implementation.'
    path_to_use = (Path(target_path) if target_path else KANBAN_FILE).resolve()
    on_copy = target_path is not None
    
    print(pdmsg("auto_75245119cf") + (pdmsg("auto_b29e4dc901") if on_copy else ""), flush=True)
    print(pdmsg("auto_8f4746fd0a", path_to_use={path_to_use}), flush=True)
    if not path_to_use.exists():
        print(pdmsg("auto_c8449c845a", path_to_use={path_to_use}))
        return False

    if not KANBAN_COLUMNS or not DONE_COLUMN:
        print(pdmsg("kanban_sort_skip_no_columns"), file=sys.stderr)
        return False
    
    # (comment)
    file_mtime = path_to_use.stat().st_mtime
    initial_mtime = file_mtime
    
    if not on_copy:
        time.sleep(0.2)
    
    # (comment)
    with open(path_to_use, 'r', encoding='utf-8') as f:
        content = f.read()
    # (comment)
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    # (comment)
    # (comment)
    section_count = len(re.findall(r'^## ', content, re.MULTILINE))
    
    # (comment)
    # (comment)
    tasks_per_section = {}
    for match in re.finditer(r'^## (.+?)$', content, re.MULTILINE):
        section_name = match.group(1).strip()
        if not section_name:
            continue
        # (comment)
        section_start = match.end()
        # (comment)
        next_match = re.search(r'^## ', content[section_start:], re.MULTILINE)
        if next_match:
            section_end = section_start + next_match.start()
        else:
            section_end = len(content)
        section_content = content[section_start:section_end]
        task_count = len(re.findall(r'^- \[[ x]\]', section_content))
        if task_count > 0:
            tasks_per_section[section_name] = task_count
    
    # (comment)
    # (comment)
    structure_broken = section_count <= 1
    
    # (comment)
    # (comment)
    # (comment)
    current_time = time.time()
    time_since_modification = current_time - file_mtime
    
    # (comment)
    # (comment)
    # (comment)
    from_sync = os.environ.get("FROM_SYNC") in ("1", "true", "yes")
    PROTECTION_WINDOW = 300  # (comment)
    if not on_copy and not from_sync and time_since_modification < PROTECTION_WINDOW and not structure_broken:
        print(
            pdmsg(
                "kanban_sort_recent_warning",
                seconds=time_since_modification,
                window=PROTECTION_WINDOW,
            )
        )
        print(pdmsg("auto_f075219b3c"))
        print(pdmsg("auto_84e6286b8c"))
        return False
    
    if structure_broken:
        print(pdmsg("auto_e4fc5fe6f8"))
        # (comment)
        # (comment)
        all_tasks = []
        task_pattern = r'(- \[[ x]\]\s+.+?)(?=\n- \[|\n## |\n%%|$)'
        for match in re.finditer(task_pattern, content, re.DOTALL):
            task_text = match.group(1).strip()
            if task_text:
                all_tasks.append(task_text)
        
        # (comment)
        sections = {col: [] for col in KANBAN_COLUMNS}
        for task_text in all_tasks:
            if re.match(r'^\s*- \[x\]', task_text):
                sections[DONE_COLUMN].append(task_text)
            else:
                sections[KANBAN_COLUMNS[0]].append(task_text)
        
        # (comment)
    else:
        sections = {}
        # (comment)
        # (comment)
        section_headers = list(re.finditer(r'^## (.+?)$', content, re.MULTILINE))
        
        for i, header_match in enumerate(section_headers):
            section_name = header_match.group(1).strip()
            if not section_name:
                continue
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
            
            section_content = content[header_start:section_end].strip()
            
            # (comment)
            # (comment)
            if '## ' in section_content:
                # (comment)
                first_header_in_content = section_content.find('## ')
                if first_header_in_content > 0:
                    section_content = section_content[:first_header_in_content].strip()
                else:
                    # (comment)
                    continue
            
            # (comment)
            tasks = []
            lines = section_content.split('\n')
            current_task = []
            
            for j, line in enumerate(lines):
                # (comment)
                if re.match(r'^\s*- \[[ x]\]', line):
                    # (comment)
                    if current_task:
                        task_text = '\n'.join(current_task).strip()
                        if task_text and task_text not in tasks:
                            tasks.append(task_text)
                    current_task = [line]
                # (comment)
                elif current_task and (line.startswith('\t') or (line.startswith('    ') and not re.match(r'^\s+- \[', line))):
                    current_task.append(line)
                # (comment)
                elif current_task and not line.strip():
                    if j + 1 < len(lines) and (lines[j+1].startswith('\t') or (lines[j+1].startswith('    ') and not re.match(r'^\s+- \[', lines[j+1]))):
                        current_task.append('')
                    else:
                        if current_task:
                            task_text = '\n'.join(current_task).strip()
                            if task_text and task_text not in tasks:
                                tasks.append(task_text)
                        current_task = []
                elif current_task and line.strip():
                    if current_task:
                        task_text = '\n'.join(current_task).strip()
                        if task_text and task_text not in tasks:
                            tasks.append(task_text)
                    current_task = []
            
            # (comment)
            if current_task:
                task_text = '\n'.join(current_task).strip()
                if task_text and task_text not in tasks:
                    tasks.append(task_text)
            
            # (comment)
            if section_name in sections:
                existing_tasks = sections[section_name]
                existing_task_texts = set(task.strip() for task in existing_tasks)
                for task in tasks:
                    task_text = task.strip()
                    if task_text and task_text not in existing_task_texts:
                        existing_tasks.append(task)
                sections[section_name] = existing_tasks
            else:
                sections[section_name] = tasks
    # (comment)
    
    def extract_priority(task_text: str) -> str:
        'Operation implementation.'
        if pdmsg("auto_1772d0120c") in task_text:
            return pdmsg("auto_3520ab2a19")
        elif pdmsg("auto_790f41adf3") in task_text:
            return pdmsg("auto_16916c0f4c")
        elif pdmsg("auto_012b8c0513") in task_text:
            return pdmsg("auto_d821e337dd")
        return ""

    # (comment)
    _NO_DEADLINE_ORDINAL = 9999999

    def extract_deadline_ordinal(task_text: str) -> Optional[int]:
        'Operation implementation.'
        match = re.search(pdmsg("auto_4f6bd2f69f"), task_text)
        if not match:
            return None
        try:
            from datetime import datetime
            dt = datetime.strptime(match.group(1), "%Y-%m-%d")
            return dt.toordinal()
        except ValueError:
            return None
    
    def sort_key(task_text: str) -> Tuple[int, int, int, str]:
        'Operation implementation.'
        deadline_ord = extract_deadline_ordinal(task_text)
        priority = extract_priority(task_text)
        pri_order = PRIORITY_ORDER.get(priority, 99)

        if deadline_ord is not None:
            # (comment)
            return (0, deadline_ord, pri_order, task_text.lower())
        # (comment)
        return (1, _NO_DEADLINE_ORDINAL, pri_order, task_text.lower())
    
    def sort_tasks_in_section(tasks: List[str]) -> List[str]:
        'Operation implementation.'
        unique_tasks = []
        seen = set()
        for task in tasks:
            first_line = task.split('\n')[0].strip()
            if first_line not in seen:
                seen.add(first_line)
                unique_tasks.append(task)
        
        return sorted(unique_tasks, key=lambda t: sort_key(t))
    
    # (comment)
    # (comment)
    done_tasks = []
    other_sections = {}
    
    for section_name, tasks in sections.items():
        if section_name == DONE_COLUMN:
            # (comment)
            other_sections[section_name] = tasks
            continue
        
        # (comment)
        remaining_tasks = []
        for task in tasks:
            # (comment)
            if re.match(r'^\s*- \[x\]', task):
                done_tasks.append(task)
            else:
                remaining_tasks.append(task)
        
        if remaining_tasks:
            other_sections[section_name] = remaining_tasks
    
    # (comment)
    if DONE_COLUMN not in other_sections:
        other_sections[DONE_COLUMN] = []
    other_sections[DONE_COLUMN].extend(done_tasks)
    
    sections = other_sections
    
    # (comment)
    total_before = sum(len(tasks) for tasks in sections.values())
    
    # (comment)
    print(pdmsg("auto_7a5d395dfd"))
    for section_name, tasks in sections.items():
        print(pdmsg("auto_a833116be6", _p1=section_name, _p3=len(tasks)))
    
    # (comment)
    unique_sections = {}
    total_after = 0
    for section_name, tasks in sections.items():
        unique_tasks = sort_tasks_in_section(tasks)
        unique_sections[section_name] = unique_tasks
        total_after += len(unique_tasks)
        if len(unique_tasks) != len(tasks):
            print(pdmsg("auto_0f04ccc82a", _p1=section_name, _p3=len(tasks), _p5=len(unique_tasks)))
    
    if total_before != total_after:
        print(pdmsg("auto_b8ec9b77e3", total_before={total_before}, total_after={total_after}))
    else:
        print(pdmsg("auto_35b72136ce", _p1=total_after, _p3=len(sections)))
    
    # (comment)
    header_match = re.search(r'^---\s*\n\s*kanban-plugin: board\s*\n---\s*\n', content, re.MULTILINE)
    if header_match:
        header = content[:header_match.end()]
    else:
        header = "---\n\nkanban-plugin: board\n\n---\n\n"
    
    settings_match = re.search(r'%% kanban:settings', content)
    if settings_match:
        footer = content[settings_match.start():]
    else:
        footer = "\n\n%% kanban:settings\n```\n{\"kanban-plugin\":\"board\"}\n```\n%%\n"
    
    new_content = header
    
    # (comment)
    column_order = KANBAN_COLUMNS
    # (comment)
    for section_name in column_order:
        new_content += f"## {section_name}\n\n"
        if section_name in unique_sections:
            sorted_tasks = unique_sections[section_name]
            for task in sorted_tasks:
                new_content += task + "\n\n"
        else:
            new_content += "\n"
    
    # (comment)
    for section_name, tasks in unique_sections.items():
        if not section_name or section_name in column_order:
            continue
        new_content += f"## {section_name}\n\n"
        for task in tasks:
            new_content += task + "\n\n"
    
    new_content += "\n" + footer
    
    # (comment)
    # (comment)
    # (comment)
    for check_attempt in range(3):
        if not on_copy:
            time.sleep(0.2)
        current_mtime = path_to_use.stat().st_mtime
        if current_mtime != initial_mtime:
            if check_attempt < 2:  # (comment)
                print(pdmsg("auto_f09ac8e22c", _p1=check_attempt + 1))
                time.sleep(0.5)  # (comment)
                continue
            else:
                # (comment)
                break
        else:
            # (comment)
            break
    else:
        # (comment)
        current_mtime = initial_mtime
    
    if current_mtime != initial_mtime and not on_copy:
        print(pdmsg("auto_a89385b994", initial_mtime={initial_mtime}, current_mtime={current_mtime}))
        print(pdmsg("auto_7edf6f7d8b"))
        
        with open(path_to_use, 'r', encoding='utf-8') as f:
            current_content = f.read()
        
        # (comment)
        # (comment)
        current_sections = {}
        current_section_headers = list(re.finditer(r'^## (.+?)$', current_content, re.MULTILINE))
        
        for i, header_match in enumerate(current_section_headers):
            section_name = header_match.group(1).strip()
            if not section_name:
                continue
            header_start = header_match.end()
            
            if i + 1 < len(current_section_headers):
                section_end = current_section_headers[i + 1].start()
            else:
                settings_match = re.search(r'%% kanban:settings', current_content[header_start:])
                if settings_match:
                    section_end = header_start + settings_match.start()
                else:
                    section_end = len(current_content)
            
            section_content = current_content[header_start:section_end].strip()
            
            # (comment)
            if '## ' in section_content:
                first_header_in_content = section_content.find('## ')
                if first_header_in_content > 0:
                    section_content = section_content[:first_header_in_content].strip()
                else:
                    continue
            
            # (comment)
            tasks = []
            lines = section_content.split('\n')
            current_task = []
            
            for j, line in enumerate(lines):
                if re.match(r'^\s*- \[[ x]\]', line):
                    if current_task:
                        task_text = '\n'.join(current_task).strip()
                        if task_text and task_text not in tasks:
                            tasks.append(task_text)
                    current_task = [line]
                elif current_task and (line.startswith('\t') or (line.startswith('    ') and not re.match(r'^\s+- \[', line))):
                    current_task.append(line)
                elif current_task and not line.strip():
                    if j + 1 < len(lines) and (lines[j+1].startswith('\t') or (lines[j+1].startswith('    ') and not re.match(r'^\s+- \[', lines[j+1]))):
                        current_task.append('')
                    else:
                        if current_task:
                            task_text = '\n'.join(current_task).strip()
                            if task_text and task_text not in tasks:
                                tasks.append(task_text)
                        current_task = []
                elif current_task and line.strip():
                    if current_task:
                        task_text = '\n'.join(current_task).strip()
                        if task_text and task_text not in tasks:
                            tasks.append(task_text)
                    current_task = []
            
            if current_task:
                task_text = '\n'.join(current_task).strip()
                if task_text and task_text not in tasks:
                    tasks.append(task_text)
            
            # (comment)
            if section_name in current_sections:
                existing_tasks = current_sections[section_name]
                existing_task_texts = set(task.strip() for task in existing_tasks)
                for task in tasks:
                    task_text = task.strip()
                    if task_text and task_text not in existing_task_texts:
                        existing_tasks.append(task)
                current_sections[section_name] = existing_tasks
            else:
                current_sections[section_name] = tasks
        
        # (comment)
        sorted_sections = {}
        for section_name, tasks in current_sections.items():
            sorted_tasks = sort_tasks_in_section(tasks)
            sorted_sections[section_name] = sorted_tasks
        
        # (comment)
        current_header_match = re.search(r'^---\s*\n\s*kanban-plugin: board\s*\n---\s*\n', current_content, re.MULTILINE)
        if current_header_match:
            current_header = current_content[:current_header_match.end()]
        else:
            current_header = "---\n\nkanban-plugin: board\n\n---\n\n"
        
        current_settings_match = re.search(r'%% kanban:settings', current_content)
        if current_settings_match:
            current_footer = current_content[current_settings_match.start():]
        else:
            current_footer = "\n\n%% kanban:settings\n```\n{\"kanban-plugin\":\"board\"}\n```\n%%\n"
        
        new_content = current_header
        
        # (comment)
        for section_name in column_order:
            new_content += f"## {section_name}\n\n"
            if section_name in sorted_sections:
                sorted_tasks = sorted_sections[section_name]
                for task in sorted_tasks:
                    new_content += task + "\n\n"
            else:
                new_content += "\n"
        
        # (comment)
        for section_name, tasks in sorted_sections.items():
            if section_name not in column_order:
                new_content += f"## {section_name}\n\n"
                for task in tasks:
                    new_content += task + "\n\n"
        
        new_content += "\n" + current_footer
        
        # (comment)
        from_sync = os.environ.get("FROM_SYNC") in ("1", "true", "yes")
        if not on_copy and not from_sync:
            for final_check in range(3):
                time.sleep(0.2)
                final_mtime = path_to_use.stat().st_mtime
                if final_mtime != current_mtime:
                    if final_check < 2:
                        print(pdmsg("auto_27211ab75c", _p1=final_check + 1))
                        time.sleep(0.5)
                        continue
                    else:
                        print(pdmsg("auto_38123c5c9a"))
                        return False
                else:
                    break
    
    # (comment)
    # (comment)
    # (comment)
    # (comment)
    input_hash = hashlib.sha1(content.encode('utf-8')).hexdigest()
    output_hash = hashlib.sha1(new_content.encode('utf-8')).hexdigest()
    if input_hash == output_hash:
        print(pdmsg("auto_6b1d122450"), flush=True)
        return True

    with open(path_to_use, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(pdmsg("auto_eda21b093c"))
    return True

