#!/usr/bin/env python3
"""Maintenance script for planning bot vault data."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TARGET = REPO / "planning_bot/services/action_logger.py"
DOMAIN = REPO / "config/domain_messages.yaml"
DOMAIN_EX = REPO / "config/domain_messages.yaml.example"

KEYS: dict[str, str] = {
    "log_entry_regex": (
        pdmsg("auto_9158eed63e")
    ),
    "logs_dir_missing": (
        pdmsg("auto_806e09aed0")
    ),
    "logs_dir_not_dir": (
        pdmsg("auto_678cec3c94")
    ),
    "logs_dir_access_denied": (
        pdmsg("auto_5e1deaac02")
    ),
    "logs_dir_empty": (
        pdmsg("auto_c6fcbf7914")
    ),
    "log_month_header": pdmsg("auto_4de56706da"),
    "log_entry_type": pdmsg("auto_0e51ea37a4"),
    "log_entry_data": pdmsg("auto_bb5b2ea1a2"),
    "history_week_header": pdmsg("auto_fcc9ff423a"),
    "history_days_empty": pdmsg("auto_e6a99a185b"),
    "history_days_header": pdmsg("auto_6c9ffb926e"),
    "movement_created": pdmsg("auto_8b5d65e49a"),
    "movement_completed": pdmsg("auto_d10b64d331"),
}


def merge_yaml(keys: dict[str, str]) -> None:
    import re as _re

    for target in (DOMAIN, DOMAIN_EX):
        if not target.exists():
            continue
        text = target.read_text(encoding="utf-8")
        if not _re.search(r"(?m)^planning:\s*$", text):
            text = text.rstrip() + "\n\nplanning:\n"
        additions: list[str] = []
        for k, v in sorted(keys.items()):
            if _re.search(rf"(?m)^  {k}:\s", text):
                continue
            if "\n" in v:
                body = "|\n" + "".join(f"  {line}\n" for line in v.splitlines())
                additions.append(f"  {k}: {body.rstrip()}\n")
            else:
                esc = v.replace("\\", "\\\\").replace('"', '\\"')
                additions.append(f'  {k}: "{esc}"\n')
        if not additions:
            continue
        m = _re.search(r"(?m)^planning:\s*$", text)
        text = text[: m.end()] + "\n" + "".join(additions) + text[m.end() :].lstrip("\n")
        target.write_text(text, encoding="utf-8")


def main() -> None:
    merge_yaml(KEYS)
    src = TARGET.read_text(encoding="utf-8")
    header = '''"""Action log read/write for planning bot."""
import json
from functools import lru_cache
import logging
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from planning_bot.core.config import ACTION_LOGS_DIR, ACTION_LOG_PREFIX, DONE_COLUMN
from planning_bot.core.pdmsg import pdmsg

_log = logging.getLogger(__name__)

_TASK_EVENT_TYPES = frozenset({"task_moved", "task_completed", "task_created"})


@lru_cache(maxsize=1)
def _log_entry_re() -> re.Pattern[str]:
    return re.compile(pdmsg("log_entry_regex"), re.DOTALL)


'''
    src = re.sub(
        r"^.*?class ActionLogger:",
        header + "class ActionLogger:",
        src,
        count=1,
        flags=re.DOTALL,
    )
    src = src.replace("_LOG_ENTRY_RE", "_log_entry_re()")
    src = src.replace(
        pdmsg("auto_670a5968e3"),
        '            return False, pdmsg("logs_dir_missing")',
    )
    src = src.replace(
        pdmsg("auto_d9c845f4f3"),
        '            return False, pdmsg("logs_dir_not_dir")',
    )
    src = src.replace(
        pdmsg("auto_d239680162"),
        '            return False, pdmsg("logs_dir_access_denied", error=e)',
    )
    src = src.replace(
        pdmsg("auto_2d9d57ac85"),
        '            return False, pdmsg("logs_dir_empty")',
    )
    src = src.replace(
        pdmsg("auto_f4d7442383"),
        '_log.debug("ActionLogger logs_dir=%s", self.logs_dir)',
    )
    src = src.replace(
        pdmsg("auto_abaef4786e"),
        'f.write(pdmsg("log_month_header", month=today.strftime("%B %Y")))',
    )
    src = src.replace(
        pdmsg("auto_11222db4c9"),
        'entry += pdmsg("log_entry_type", action_type=action_type)',
    )
    src = src.replace(
        pdmsg("auto_2fac145f39"),
        'entry += pdmsg("log_entry_data", payload=json.dumps(data, ensure_ascii=False, indent=2))',
    )
    src = src.replace(
        pdmsg("auto_4dfb20eec4"),
        'result = pdmsg("history_week_header", week_start=week_start_str)',
    )
    src = src.replace(
        pdmsg("auto_e9c5140f6d"),
        'return pdmsg("history_days_empty", days=max(1, days))',
    )
    src = src.replace(
        pdmsg("auto_8b7416725c"),
        'result = pdmsg("history_days_header", days=max(1, days), period_start=period_start_str)',
    )
    src = src.replace(
        pdmsg("auto_8844479596"),
        'movement_chain.append(pdmsg("movement_created", timestamp=entry["timestamp"]))',
    )
    src = src.replace(
        pdmsg("auto_33104fbe41"),
        'movement_chain.append(pdmsg("movement_completed", timestamp=entry["timestamp"]))',
    )
    TARGET.write_text(src, encoding="utf-8")
    print("action_logger patched")


if __name__ == "__main__":
    main()
