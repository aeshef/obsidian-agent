#!/usr/bin/env python3
"""Atomically pull production goals mapping from server to local vault."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from planning_bot.core.config import MAPPING_FILE, VAULT_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", type=Path, default=MAPPING_FILE)
    parser.add_argument("--server", default=os.environ.get("SERVER", ""))
    parser.add_argument("--server-vault", default=os.environ.get("SERVER_VAULT", ""))
    args = parser.parse_args()

    if not args.server or not args.server_vault:
        print("SERVER and SERVER_VAULT env vars are required", file=sys.stderr)
        return 1

    local = args.local.expanduser().resolve()
    try:
        rel = local.relative_to(VAULT_PATH.resolve())
    except ValueError:
        print(f"local path must be inside vault ({VAULT_PATH})", file=sys.stderr)
        return 1

    remote = f"{args.server}:{args.server_vault}/{rel.as_posix()}"
    tmp = local.with_suffix(local.suffix + ".pull.tmp")
    local.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(["rsync", "-av", remote, str(tmp)], check=True)
    os.replace(tmp, local)
    print(f"pulled {remote} -> {local}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
