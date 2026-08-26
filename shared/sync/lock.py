"""Sync lock helpers (carved out of obsidian_sync.sh)."""
from __future__ import annotations

import time
from pathlib import Path


def lock_age_seconds(lock_path: Path) -> int:
    try:
        return int(time.time() - lock_path.stat().st_mtime)
    except OSError:
        return 0


def is_stale_lock(lock_path: Path, *, stale_sec: int = 7200) -> bool:
    if not lock_path.exists():
        return False
    return lock_age_seconds(lock_path) > stale_sec
