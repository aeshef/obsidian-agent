"""Load repo .env into os.environ (idempotent, no overwrite)."""
from __future__ import annotations

import os
import re
from pathlib import Path

_KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


def repo_root_from_here(start: Path | None = None) -> Path:
    cur = (start or Path(__file__)).resolve()
    for parent in [cur, *cur.parents]:
        if (parent / "unified_bot").is_dir() and (parent / "scripts" / "setup.sh").is_file():
            return parent
    return Path(__file__).resolve().parents[2]


def load_repo_env(root: Path | None = None) -> Path | None:
    """Parse repo .env; set keys not already in os.environ. Returns .env path or None."""
    base = root or repo_root_from_here()
    env = base / ".env"
    if not env.is_file():
        return None
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _KEY_RE.match(line)
        if not m:
            continue
        key = m.group(1)
        if key in os.environ and str(os.environ.get(key, "")).strip():
            continue
        _, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        os.environ[key] = val
    os.environ.setdefault("AGENT_ROOT", str(base))
    return env
