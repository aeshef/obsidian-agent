"""Exclusive lock for routines markdown (same process + cross-process)."""
from __future__ import annotations

import fcntl
import threading
from contextlib import contextmanager
from pathlib import Path

_thread_locks: dict[str, threading.Lock] = {}


def _key(path: Path) -> str:
    return str(path.resolve())


@contextmanager
def routines_transaction(path: Path):
    """One load→mutate→save must run inside this (bot check-in / cron / sync)."""
    key = _key(path)
    tlock = _thread_locks.setdefault(key, threading.Lock())
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with tlock:
        with open(lock_path, "a+", encoding="utf-8") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
