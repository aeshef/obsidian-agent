#!/usr/bin/env python3
"""Print shell exports for vault_paths.yaml (folder names for obsidian_sync.sh)."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.capabilities.vault_paths_shell import export_shell_env


def main() -> int:
    print(export_shell_env(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
