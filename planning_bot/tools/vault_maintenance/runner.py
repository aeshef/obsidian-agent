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


from planning_bot.tools.vault_maintenance.kanban_ids import add_ids_to_tasks
from planning_bot.tools.vault_maintenance.kanban_sort import sort_kanban_tasks
from planning_bot.tools.vault_maintenance.kanban_state import (
    get_kanban_state,
    get_task_title_by_id,
    log_task_movements,
)
from planning_bot.tools.vault_maintenance.quarterly import sync_quarterly_focus

def run_all() -> bool:
    'Operation implementation.'
    print("=" * 50)
    print(pdmsg("auto_c27a77b356"))
    print("=" * 50)
    print()
    
    results = []
    
    # (comment)
    state_file = LOGS_DIR / "kanban_state.json"
    previous_state = {}
    if state_file.exists():
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                previous_state = json.load(f)
            
            # (comment)
            # (comment)
            if previous_state and any('|' in key or (not key.startswith('h') and len(key) > 8) for key in previous_state.keys()):
                # (comment)
                current_state_temp = get_kanban_state()
                migrated_state = {}
                
                # (comment)
                with open(KANBAN_FILE, 'r', encoding='utf-8') as f:
                    kanban_content = f.read()
                
                for old_key, old_column in previous_state.items():
                    # (comment)
                    if len(old_key) == 8 and all(c in '0123456789abcdef' for c in old_key):
                        migrated_state[old_key] = old_column
                    elif '|' in old_key:
                        # (comment)
                        date, old_name = old_key.split('|', 1)
                        found = False
                        for task_id, _ in current_state_temp.items():
                            task_title = get_task_title_by_id(task_id, kanban_content)
                            if task_title == old_name:
                                migrated_state[task_id] = old_column
                                found = True
                                break
                        
                        if not found:
                            # (comment)
                            hash_str = f"{date}|{old_name}"
                            task_id = hashlib.md5(hash_str.encode('utf-8')).hexdigest()[:8]
                            migrated_state[task_id] = old_column
                    else:
                        # (comment)
                        found = False
                        for task_id, _ in current_state_temp.items():
                            task_title = get_task_title_by_id(task_id, kanban_content)
                            if task_title == old_key:
                                migrated_state[task_id] = old_column
                                found = True
                                break
                        
                        if not found:
                            # (comment)
                            task_id = hashlib.md5(old_key.encode('utf-8')).hexdigest()[:8]
                            migrated_state[task_id] = old_column
                
                previous_state = migrated_state
        except Exception as e:
            print(pdmsg("auto_6d89225ebc", e={e}))
            previous_state = {}
    
    current_state_before = get_kanban_state()
    
    # (comment)
    results.append((pdmsg("auto_bfafe7b122"), add_ids_to_tasks()))
    print()
    
    # (comment)
    results.append((pdmsg("auto_46498478d3"), sync_quarterly_focus()))
    print()
    
    # (comment)
    results.append((pdmsg("auto_28dd89327d"), sort_kanban_tasks()))
    print()
    
    # (comment)
    try:
        from planning_bot.services.action_logger import ActionLogger
        logger = ActionLogger(logs_dir=ACTION_LOGS_DIR)
        log_task_movements(logger, previous_state, current_state_before)
    except Exception as e:
        print(pdmsg("auto_a38eb0d300", e={e}))
    
    # (comment)
    try:
        current_state_after = get_kanban_state()  # (comment)
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(current_state_after, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(pdmsg("auto_ee4a301644", e={e}))
    
    # (comment)
    # (comment)
    pass

    # (comment)
    try:
        from planning_bot.tools.calendar_sync import run_calendar_sync
        results.append((pdmsg("auto_a21f528d0e"), run_calendar_sync()))
    except Exception as e:
        print(pdmsg("auto_e4fb55b904", e={e}))
        results.append((pdmsg("auto_a21f528d0e"), False))

    # (comment)
    try:
        from planning_bot.tools.context_sync import run_context_sync
        results.append((pdmsg("auto_ceb999b90b"), run_context_sync()))
    except Exception as e:
        print(pdmsg("auto_3e262ecd98", e={e}))
        results.append((pdmsg("auto_ceb999b90b"), False))
    print()

    # (comment)
    # (comment)
    if os.environ.get("GMAIL_IMAP_USER") and os.environ.get("GMAIL_IMAP_APP_PASSWORD"):
        try:
            from planning_bot.tools.iphone_mail_sync import run_iphone_mail_sync

            # (comment)
            _to = os.environ.get("IPHONE_MAIL_SYNC_TODAY_ONLY", "1").lower() not in (
                "0",
                "false",
                "no",
                "off",
            )
            res = run_iphone_mail_sync(today_only=_to)
            ok = res.get("ok", False)
            written = res.get("written", 0)
            print(
                f"   iphone_mail_sync: ok={ok} written={written} today_only={res.get('today_only')}"
                + (f" errors={res.get('errors')}" if res.get("errors") else ""),
                flush=True,
            )
            results.append(("iPhone mail sync", ok or written == 0))
        except Exception as e:
            print(pdmsg("auto_a9432c09f4", e={e}))
            results.append(("iPhone mail sync", False))
    else:
        print(pdmsg("auto_682c2ca2df"), flush=True)
    print()

    # (comment)
    try:
        from planning_bot.tools.iphone_context_sync import run_iphone_context_sync

        results.append((pdmsg("auto_e89925dc1d"), run_iphone_context_sync()))
    except Exception as e:
        print(pdmsg("auto_07ef8b5691", e={e}))
        results.append((pdmsg("auto_e89925dc1d"), False))
    print()

    # (comment)
    print("=" * 50)
    print(pdmsg("auto_04198f3dd8"))
    print("=" * 50)
    
    success_count = sum(1 for _, success in results if success)
    total_count = len(results)
    
    for name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {name}")
    
    print()
    print(pdmsg("auto_a7bcafbceb", success_count={success_count}, total_count={total_count}))
    
    return success_count == total_count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids-only", action="store_true", help=pdmsg("auto_c2c2a91e94"))
    args = parser.parse_args()
    if args.ids_only:
        success = add_ids_to_tasks()
    else:
        success = run_all()
    sys.exit(0 if success else 1)
