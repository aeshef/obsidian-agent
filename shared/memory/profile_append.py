"""Pending appends to user_profile.md — confirm required (never auto-write)."""
from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shared.memory.config import global_profile_path, load_memory_config
from shared.memory.insights import memory_db_path

log = logging.getLogger("shared.memory.profile_append")

_lock = threading.Lock()
_ready = False

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profile_append_pending (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  text TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_profile_append_user
  ON profile_append_pending(user_id, status);
"""


def _cfg() -> dict:
    block = load_memory_config().get("profile_append") or {}
    return block if isinstance(block, dict) else {}


def section_header() -> str:
    return str(_cfg().get("section_header") or "## Agent notes").strip() or "## Agent notes"


def max_chars() -> int:
    try:
        return max(40, int(_cfg().get("max_chars") or 500))
    except (TypeError, ValueError):
        return 500


def pending_ttl_hours() -> int:
    try:
        return max(1, int(_cfg().get("pending_ttl_hours") or 48))
    except (TypeError, ValueError):
        return 48


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure() -> None:
    global _ready
    if _ready:
        return
    path = memory_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()
    _ready = True


def propose(user_id: int, text: str) -> tuple[int | None, str]:
    body = (text or "").strip()
    if not body:
        return None, "empty"
    if len(body) > max_chars():
        body = body[: max_chars()]
    _ensure()
    with _lock:
        with sqlite3.connect(str(memory_db_path())) as conn:
            cur = conn.execute(
                "INSERT INTO profile_append_pending(user_id, text, status, created_at) "
                "VALUES(?,?, 'pending', ?)",
                (int(user_id), body, _now()),
            )
            conn.commit()
            return int(cur.lastrowid), body


def list_pending(user_id: int) -> list[dict]:
    _ensure()
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=pending_ttl_hours())
    ).isoformat(timespec="seconds")
    with sqlite3.connect(str(memory_db_path())) as conn:
        conn.execute(
            "UPDATE profile_append_pending SET status='expired' "
            "WHERE user_id=? AND status='pending' AND created_at < ?",
            (int(user_id), cutoff),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT id, text, created_at FROM profile_append_pending "
            "WHERE user_id=? AND status='pending' ORDER BY id DESC LIMIT 20",
            (int(user_id),),
        ).fetchall()
    return [{"id": r[0], "text": r[1], "created_at": r[2]} for r in rows]


def _append_to_profile(text: str) -> Path:
    path = global_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    header = section_header()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    block = f"- ({stamp}) {text.strip()}\n"
    if path.is_file():
        content = path.read_text(encoding="utf-8")
        if header in content:
            # Append under existing section (before next ## or EOF).
            before, rest = content.split(header, 1)
            if "\n## " in rest:
                sec, after = rest.split("\n## ", 1)
                new_sec = sec.rstrip() + "\n" + block + "\n"
                content = before + header + new_sec + "## " + after
            else:
                content = before + header + rest.rstrip() + "\n" + block
        else:
            content = content.rstrip() + f"\n\n{header}\n\n{block}"
    else:
        content = f"{header}\n\n{block}"
    path.write_text(content, encoding="utf-8")
    return path


def confirm(user_id: int, pending_id: int) -> tuple[bool, str]:
    _ensure()
    with _lock:
        with sqlite3.connect(str(memory_db_path())) as conn:
            row = conn.execute(
                "SELECT text FROM profile_append_pending "
                "WHERE id=? AND user_id=? AND status='pending'",
                (int(pending_id), int(user_id)),
            ).fetchone()
            if not row:
                return False, ""
            text = str(row[0])
            try:
                path = _append_to_profile(text)
            except OSError as e:
                log.warning("profile append write failed: %s", e)
                return False, ""
            conn.execute(
                "UPDATE profile_append_pending SET status='confirmed' WHERE id=?",
                (int(pending_id),),
            )
            conn.commit()
    return True, str(path.name)


def reject(user_id: int, pending_id: int) -> bool:
    _ensure()
    with _lock:
        with sqlite3.connect(str(memory_db_path())) as conn:
            cur = conn.execute(
                "UPDATE profile_append_pending SET status='rejected' "
                "WHERE id=? AND user_id=? AND status='pending'",
                (int(pending_id), int(user_id)),
            )
            conn.commit()
            return cur.rowcount > 0
