"""Unified log format for all monorepo bots."""
from __future__ import annotations

import logging
import sys

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def setup_logging(
    level: int | str = logging.INFO,
    *,
    fmt: str = _DEFAULT_FORMAT,
    stream=None,
) -> None:
    """Idempotent root logger setup (does not duplicate handlers)."""
    root = logging.getLogger()
    if getattr(setup_logging, "_configured", False):
        root.setLevel(level)
        return
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(handler)
    root.setLevel(level)
    setup_logging._configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def add_rotating_file_handler(
    log_dir,
    *,
    filename: str = "bot.log",
    max_bytes: int = 5_000_000,
    backup_count: int = 3,
    level: int | str = logging.INFO,
) -> None:
    """File log with rotation (idempotent — one FileHandler per directory)."""
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    target = str(log_path / filename)
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == target:
            return
    fh = RotatingFileHandler(target, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    fh.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    fh.setLevel(level)
    root.addHandler(fh)
