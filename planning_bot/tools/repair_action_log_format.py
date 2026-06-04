#!/usr/bin/env python3
"""Repair action log markdown corrupted by action_type={action_type} set bug."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_AGENT = Path(__file__).resolve().parent.parent.parent
if str(_AGENT) not in sys.path:
    sys.path.insert(0, str(_AGENT))

from planning_bot.core.config import ACTION_LOG_PREFIX, ACTION_LOGS_DIR
from planning_bot.services.action_log_format import repair_log_text as repair_text


def push_logs_to_server(logs_dir: Path, month: str) -> int:
    """Push repaired logs to VPS (obsidian_sync excludes Логи/ on push)."""
    import os
    import subprocess

    server = os.environ.get("OBSIDIAN_SERVER", "obsidian-server")
    vault = os.environ.get("SERVER_VAULT", "/root/obsidian-vault")
    rel = logs_dir.name
    parent = logs_dir.parent.name
    remote = f"{server}:{vault}/{parent}/{rel}/"
    pattern = f"{ACTION_LOG_PREFIX}{month}.md" if month else f"{ACTION_LOG_PREFIX}*.md"
    files = sorted(logs_dir.glob(pattern))
    if not files:
        return 1
    rsync = os.environ.get("RSYNC_BIN", "rsync")
    rsh = os.environ.get(
        "RSYNC_RSH",
        "ssh -o UseKeychain=yes -o BatchMode=yes -o ConnectTimeout=10",
    )
    for path in files:
        cmd = [rsync, "-avz", "-e", rsh, str(path), remote]
        print("push:", " ".join(cmd))
        subprocess.run(cmd, check=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vault", type=Path, default=None)
    ap.add_argument("--month", default="", help="YYYY-MM or empty = all *Логи_Действий_*.md")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--push-server",
        action="store_true",
        help="After repair, rsync log file(s) to OBSIDIAN_SERVER (bypasses obsidian_sync exclude)",
    )
    args = ap.parse_args()

    logs_dir = ACTION_LOGS_DIR
    if args.vault:
        from shared.vault_paths_config import dashboards_sub, folder, vault_file

        logs_dir = (
            Path(args.vault).expanduser()
            / folder("dashboards")
            / dashboards_sub("logs")
        )

    pattern = f"{ACTION_LOG_PREFIX}{args.month}.md" if args.month else f"{ACTION_LOG_PREFIX}*.md"
    files = sorted(logs_dir.glob(pattern))
    if not files:
        print(f"No files matching {pattern} in {logs_dir}", file=sys.stderr)
        return 1

    total = 0
    for path in files:
        raw = path.read_text(encoding="utf-8")
        fixed, n = repair_text(raw)
        if n == 0:
            print(f"{path.name}: ok")
            continue
        print(f"{path.name}: repaired {n} entries")
        total += n
        if not args.dry_run:
            path.write_text(fixed, encoding="utf-8")

    print(f"Done. Total repairs: {total}")
    if args.push_server and not args.dry_run:
        return push_logs_to_server(logs_dir, args.month)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
