"""Bootstrap helpers for standalone scripts; host entry re-exported lazily."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_MONOREPO_ROOT = Path(__file__).resolve().parent.parent


def setup_bot(component: str) -> None:
    """Insert monorepo + bot package on sys.path; load .env for CLI scripts."""
    bot_root = _MONOREPO_ROOT / component
    if not bot_root.is_dir():
        raise FileNotFoundError(f"setup_bot: missing {bot_root}")
    os.environ.setdefault("AGENT_ROOT", str(_MONOREPO_ROOT))
    for p in (str(bot_root), str(_MONOREPO_ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)
    for env_path in (_MONOREPO_ROOT / ".env", bot_root / ".env"):
        if not env_path.is_file():
            continue
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def resolve_host_token(*args: Any, **kwargs: Any) -> Any:
    from unified_bot.host.bootstrap import resolve_host_token as _impl

    return _impl(*args, **kwargs)


def run_host_bot(*args: Any, **kwargs: Any) -> Any:
    from unified_bot.host.bootstrap import run_host_bot as _impl

    return _impl(*args, **kwargs)


__all__ = ["setup_bot", "resolve_host_token", "run_host_bot"]
