from planning_bot.core.pdmsg import pdmsg, pdmsg_nl
from pathlib import Path
from datetime import datetime, timezone
import re
from typing import Dict, List, Tuple

from planning_bot.core.config import VAULT_PATH
from shared.tz import get_tz

ROUTINES_DIR = VAULT_PATH / pdmsg("auto_9e515fb7c8") / pdmsg("auto_fc906f665b")
CONFIG_FILE = ROUTINES_DIR / pdmsg("auto_f9a9071bae")
TODAY_FILE = ROUTINES_DIR / pdmsg("auto_2cc3b7c2af")
HISTORY_FILE = ROUTINES_DIR / pdmsg("auto_1c178f6429")

msk_tz = get_tz()


def load_tasks_config() -> Tuple[List[str], List[str], List[str]]:
    'Operation implementation.'
    if not CONFIG_FILE.exists():
        return [], [], []
    
    content = CONFIG_FILE.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    morning_tasks = []
    day_tasks = []
    evening_tasks = []
    current_section = None
    
    for line in lines:
        if pdmsg("auto_87b10eda1f") in line:
            current_section = "morning"
            continue
        elif pdmsg("auto_3ed8660b4d") in line:
            current_section = "day"
            continue
        elif pdmsg("auto_0f1e39b138") in line:
            current_section = "evening"
            continue
        elif line.strip().startswith('- ') and current_section:
            task = line.strip()[2:].strip()  # (comment)
            if current_section == "morning":
                morning_tasks.append(task)
            elif current_section == "day":
                day_tasks.append(task)
            else:
                evening_tasks.append(task)
    
    return morning_tasks, day_tasks, evening_tasks


def load_today_status() -> Dict[str, Dict[str, bool]]:
    'Operation implementation.'
    if not TODAY_FILE.exists():
        return {"morning": {}, "day": {}, "evening": {}}
    
    content = TODAY_FILE.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    status = {"morning": {}, "day": {}, "evening": {}}
    current_section = None
    
    for line in lines:
        if pdmsg("auto_87b10eda1f") in line:
            current_section = "morning"
            continue
        elif pdmsg("auto_3ed8660b4d") in line:
            current_section = "day"
            continue
        elif pdmsg("auto_0f1e39b138") in line:
            current_section = "evening"
            continue
        elif line.strip().startswith('- ['):
            match = re.match(r'-\s*\[([ x])\]\s*(.+)', line.strip())
            if match and current_section:
                is_checked = match.group(1) == 'x'
                task = match.group(2).strip()
                status[current_section][task] = is_checked
    
    return status


def get_today_date() -> str:
    'Operation implementation.'
    now_utc = datetime.now(timezone.utc)
    now_msk = now_utc.astimezone(msk_tz)
    return now_msk.strftime("%Y-%m-%d")


def format_status_for_history(morning_tasks_config: List[str], day_tasks_config: List[str], evening_tasks_config: List[str],
                             today_status: Dict[str, Dict[str, bool]], date_to_save: str = None) -> str:
    'Operation implementation.'
    from datetime import timedelta
    
    lines = []
    
    # (comment)
    if date_to_save:
        date_str = date_to_save
    else:
        # (comment)
        now_utc = datetime.now(timezone.utc)
        now_msk = now_utc.astimezone(msk_tz)
        yesterday_msk = now_msk - timedelta(days=1)
        date_str = yesterday_msk.strftime("%Y-%m-%d")
    
    lines.append(f"## {date_str}")
    lines.append("")
    lines.append(pdmsg("auto_7336f91797"))
    for task in morning_tasks_config:
        checked = today_status["morning"].get(task, False)
        lines.append(f"- {'✅' if checked else '⬜'} {task}")
    lines.append("")
    lines.append(pdmsg("auto_c9ee65efdc"))
    for task in day_tasks_config:
        checked = today_status["day"].get(task, False)
        lines.append(f"- {'✅' if checked else '⬜'} {task}")
    lines.append("")
    lines.append(pdmsg("auto_3e5b0bed8a"))
    for task in evening_tasks_config:
        checked = today_status["evening"].get(task, False)
        lines.append(f"- {'✅' if checked else '⬜'} {task}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    return '\n'.join(lines)


def update_today_file(morning_tasks: List[str], day_tasks: List[str], evening_tasks: List[str]):
    'Operation implementation.'
    # pdmsg_nl: dmsg().strip() eats newlines after YAML | blocks — header and checkboxes merge
    content = pdmsg_nl("auto_fdcaa6c39c")

    for task in morning_tasks:
        content += f"- [ ] {task}\n"

    content += "\n" + pdmsg_nl("auto_9d4f2e369f")

    for task in day_tasks:
        content += f"- [ ] {task}\n"

    content += "\n" + pdmsg_nl("auto_4b9557a6cd")
    
    for task in evening_tasks:
        content += f"- [ ] {task}\n"
    
    content += "\n---\n\n"
    content += pdmsg("auto_ef879a3e9b", p1=get_today_date()) 
    TODAY_FILE.write_text(content, encoding='utf-8')


def append_to_history(history_entry: str):
    'Operation implementation.'
    if HISTORY_FILE.exists():
        current_content = HISTORY_FILE.read_text(encoding='utf-8')
        # (comment)
        header_end = current_content.find("---")
        if header_end != -1:
            header = current_content[:header_end + 3]
            rest = current_content[header_end + 3:].lstrip()
            new_content = header + "\n\n" + history_entry + rest
        else:
            new_content = current_content + "\n\n" + history_entry
    else:
        new_content = pdmsg("auto_a55cff26c3", p1=history_entry)
    
    HISTORY_FILE.write_text(new_content, encoding='utf-8')


def check_and_update():
    'Operation implementation.'
    morning_tasks_config, day_tasks_config, evening_tasks_config = load_tasks_config()
    
    if not morning_tasks_config and not day_tasks_config and not evening_tasks_config:
        # (comment)
        return
    
    # (comment)
    today_status = load_today_status()
    
    # (comment)
    current_date = get_today_date()
    
    # (comment)
    if TODAY_FILE.exists():
        content = TODAY_FILE.read_text(encoding='utf-8')
        date_match = re.search(pdmsg("auto_f4000b502c"), content)
        if date_match:
            file_date = date_match.group(1)
            
            # (comment)
            if file_date < current_date:
                # (comment)
                # (comment)
                history_entry = format_status_for_history(
                    morning_tasks_config, day_tasks_config, evening_tasks_config, today_status, file_date
                )
                append_to_history(history_entry)
                # (comment)
                update_today_file(morning_tasks_config, day_tasks_config, evening_tasks_config)
                return
            elif file_date == current_date:
                # (comment)
                return
            else:
                # (comment)
                return
    
    # (comment)
    if not TODAY_FILE.exists():
        update_today_file(morning_tasks_config, day_tasks_config, evening_tasks_config)
        return
    
    # (comment)
    # (comment)
    content = TODAY_FILE.read_text(encoding='utf-8')
    current_tasks_in_file = set()
    in_morning = False
    in_day = False
    in_evening = False
    for line in content.split('\n'):
        if pdmsg("auto_87b10eda1f") in line:
            in_morning = True
            in_day = False
            in_evening = False
            continue
        elif pdmsg("auto_3ed8660b4d") in line:
            in_morning = False
            in_day = True
            in_evening = False
            continue
        elif pdmsg("auto_0f1e39b138") in line:
            in_morning = False
            in_day = False
            in_evening = True
            continue
        elif line.strip().startswith('- ['):
            match = re.match(r'-\s*\[[ x]\]\s*(.+)', line.strip())
            if match:
                task = match.group(1).strip()
                if in_morning:
                    section = "morning"
                elif in_day:
                    section = "day"
                else:
                    section = "evening"
                current_tasks_in_file.add((task, section))
    
    config_tasks = set()
    for task in morning_tasks_config:
        config_tasks.add((task, "morning"))
    for task in day_tasks_config:
        config_tasks.add((task, "day"))
    for task in evening_tasks_config:
        config_tasks.add((task, "evening"))
    
    # (comment)
    if current_tasks_in_file != config_tasks:
        # (comment)
        preserved_status = {"morning": {}, "day": {}, "evening": {}}
        for task_name, section in current_tasks_in_file:
            if (task_name, section) in config_tasks:
                preserved_status[section][task_name] = today_status[section].get(task_name, False)
        
        # (comment)
        update_today_file(morning_tasks_config, day_tasks_config, evening_tasks_config)
        
        # (comment)
        # (comment)


if __name__ == "__main__":
    check_and_update()
