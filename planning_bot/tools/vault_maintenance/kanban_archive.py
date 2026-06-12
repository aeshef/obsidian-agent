#!/usr/bin/env python3
"""Move done tasks from active board to archive (monthly calendar boundary)."""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from planning_bot.core.config import (
    ACTION_LOGS_DIR,
    DONE_COLUMN,
    KANBAN_COLUMNS,
    KANBAN_FILE,
    LOGS_DIR,
)
from planning_bot.core.pdmsg import pdmsg
from planning_bot.services import kanban_parse as kp
from planning_bot.services.kanban_lock import kanban_transaction
from shared.agent.platform_config import platform_int
from shared.kanban_paths import kanban_archive_enabled, kanban_archive_path
from shared.parsing.iso_date import parse_iso_calendar_day


def _archive_meta_path() -> Path:
    return LOGS_DIR / "kanban_archive_meta.json"


def _load_meta() -> dict:
    path = _archive_meta_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_meta(meta: dict) -> None:
    path = _archive_meta_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _schema_archive_section_template() -> str:
    from planning_bot.core.config import _kanban_schema

    block = _kanban_schema().get("archive") or {}
    tpl = block.get("section_title_template")
    return str(tpl) if tpl else "{done_column} · {year}-{month:02d}"


def _month_section_title(year: int, month: int) -> str:
    tpl = _schema_archive_section_template()
    return tpl.format(done_column=DONE_COLUMN, year=year, month=month)


def _parse_archive_sections(content: str) -> Dict[str, List[str]]:
    sections = kp.parse_sections(content)
    out: Dict[str, List[str]] = {}
    for col, blocks in sections.items():
        out.setdefault(col, []).extend(blocks)
    return out


def _archive_header_title() -> str:
    archive_path = kanban_archive_path()
    if archive_path is None:
        return pdmsg("kanban_archive_default_title")
    stem = archive_path.stem.lstrip("📦").strip()
    return stem or pdmsg("kanban_archive_default_title")


def _ensure_archive_skeleton() -> Path:
    archive_path = kanban_archive_path()
    if archive_path is None:
        raise RuntimeError("kanban_archive_board not configured")
    if not archive_path.parent.is_dir():
        archive_path.parent.mkdir(parents=True, exist_ok=True)
    if not archive_path.is_file():
        title = _archive_header_title()
        archive_path.write_text(f"# {title}\n\n", encoding="utf-8")
    return archive_path


def _completion_dates_from_logs() -> Dict[str, date]:
    from planning_bot.core.config import ACTION_LOG_PREFIX
    from planning_bot.services.action_logger import ActionLogger

    logger = ActionLogger(logs_dir=ACTION_LOGS_DIR)
    out: Dict[str, date] = {}
    logs_dir = ACTION_LOGS_DIR
    if not logs_dir.is_dir():
        return out

    files = sorted(logs_dir.glob(f"{ACTION_LOG_PREFIX}*.md"))
    entry_re = re.compile(pdmsg("auto_9158eed63e"), re.DOTALL)

    for log_file in files:
        try:
            content = log_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in entry_re.finditer(content):
            if match.group(2) != "task_completed":
                continue
            try:
                ts = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                data = json.loads(match.group(3))
            except (ValueError, json.JSONDecodeError, TypeError):
                continue
            tid = (data.get("task_id") or "").strip().lower()
            if tid:
                out[tid] = ts.date()
    return out


def _task_completion_date(
    block: str,
    task_id: Optional[str],
    completion_by_id: Dict[str, date],
) -> Optional[date]:
    if task_id and task_id in completion_by_id:
        return completion_by_id[task_id]
    meta = kp.metadata_from_block(block)
    created = meta.get("created_date")
    if created:
        return parse_iso_calendar_day(str(created))
    return None


def _rebuild_active_content(original: str, sections: Dict[str, List[str]]) -> str:
    from planning_bot.services.kanban_agent import _rebuild_kanban_content

    return _rebuild_kanban_content(sections, original)


def _rebuild_archive_content(header: str, sections: Dict[str, List[str]]) -> str:
    lines = [header.rstrip()]
    if not header.endswith("\n"):
        lines[0] += "\n"
    for col in sorted(sections.keys(), reverse=True):
        blocks = sections[col]
        if not blocks:
            continue
        lines.append(f"## {col}\n")
        for block in blocks:
            lines.append(block)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _sync_monitor_after_archive() -> None:
    try:
        from planning_bot.services.kanban_monitor import KanbanMonitor

        monitor = KanbanMonitor()
        active_state = monitor.load_state_from_markdown()
        monitor.last_state = active_state
        if active_state:
            import hashlib

            monitor.last_state_hash = hashlib.md5(
                json.dumps(active_state, sort_keys=True).encode()
            ).hexdigest()
        else:
            monitor.last_state_hash = None
        monitor._save_monitor_state()
        from planning_bot.tools.vault_maintenance.kanban_state import get_kanban_state

        merged = get_kanban_state()
        monitor._save_kanban_state_json(merged)
    except Exception as e:
        print(pdmsg("kanban_archive_monitor_sync_warn", e=e), flush=True)


def archive_done_tasks(dry_run: bool = False) -> bool:
    """Archive done tasks completed before the current calendar month."""
    if not kanban_archive_enabled():
        print(pdmsg("kanban_archive_skip_disabled"), flush=True)
        return True

    if not KANBAN_FILE.is_file():
        print(pdmsg("auto_11757cfc8b", KANBAN_FILE=KANBAN_FILE), flush=True)
        return False

    month_key = date.today().strftime("%Y-%m")
    meta = _load_meta()
    if meta.get("last_archive_month") == month_key:
        print(pdmsg("kanban_archive_skip_month", month=month_key), flush=True)
        return True

    cutoff = date.today().replace(day=1)
    completion_by_id = _completion_dates_from_logs()

    with open(KANBAN_FILE, "r", encoding="utf-8") as f:
        active_content = f.read()

    sections = kp.parse_sections(active_content)
    done_blocks = list(sections.get(DONE_COLUMN, []))
    if not done_blocks:
        meta["last_archive_month"] = month_key
        _save_meta(meta)
        print(pdmsg("kanban_archive_nothing_done"), flush=True)
        return True

    to_archive: List[Tuple[str, str, date]] = []
    keep_done: List[str] = []

    for block in done_blocks:
        tid = kp.extract_id_from_block(block)
        tid_key = tid.lower() if tid else ""
        comp = _task_completion_date(block, tid_key, completion_by_id)
        if comp is None or comp < cutoff:
            if comp:
                month_title = _month_section_title(comp.year, comp.month)
            else:
                month_title = _month_section_title(cutoff.year, 1)
            to_archive.append((month_title, block, comp))
        else:
            keep_done.append(block)

    if not to_archive:
        meta["last_archive_month"] = month_key
        _save_meta(meta)
        print(pdmsg("kanban_archive_keep_current_month", month=month_key), flush=True)
        return True

    print(
        pdmsg(
            "kanban_archive_plan",
            count=len(to_archive),
            keep=len(keep_done),
            cutoff=cutoff.isoformat(),
        ),
        flush=True,
    )

    if dry_run:
        return True

    archive_path = _ensure_archive_skeleton()
    archive_content = archive_path.read_text(encoding="utf-8")
    archive_sections = _parse_archive_sections(archive_content)

    for month_title, block, _ in to_archive:
        archive_sections.setdefault(month_title, []).append(block)

    sections[DONE_COLUMN] = keep_done
    new_active = _rebuild_active_content(active_content, sections)

    header_match = re.match(r"(#.*?\n(?:\n|.)*?)(?=## |\Z)", archive_content, re.DOTALL)
    header = header_match.group(1) if header_match else f"# {_archive_header_title()}\n\n"
    new_archive = _rebuild_archive_content(header, archive_sections)

    from_sync = os.environ.get("FROM_SYNC", "").strip().lower() in ("1", "true", "yes")
    if not from_sync:
        print(pdmsg("kanban_archive_skip_not_from_sync"), flush=True)
        return True

    with kanban_transaction(KANBAN_FILE):
        KANBAN_FILE.write_text(new_active, encoding="utf-8")
    with kanban_transaction(archive_path):
        archive_path.write_text(new_archive, encoding="utf-8")

    meta["last_archive_month"] = month_key
    meta["last_archive_count"] = len(to_archive)
    meta["last_archive_at"] = datetime.now().isoformat(timespec="seconds")
    _save_meta(meta)

    _sync_monitor_after_archive()
    print(pdmsg("kanban_archive_done", count=len(to_archive)), flush=True)
    return True
