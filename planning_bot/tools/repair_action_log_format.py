#!/usr/bin/env python3
"""Repair action log markdown (---## glue, wrong **Тип:** line).

Run separately on Mac vault and on VPS — logs are not synced via obsidian_sync.
  Local:  python3 planning_bot/tools/repair_action_log_format.py --month 2026-06
  VPS:    python3 planning_bot/tools/repair_action_log_format.py --remote --month 2026-06
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_AGENT = Path(__file__).resolve().parent.parent.parent
if str(_AGENT) not in sys.path:
    sys.path.insert(0, str(_AGENT))

from planning_bot.core.config import ACTION_LOG_PREFIX, ACTION_LOGS_DIR
from planning_bot.services.action_log_format import repair_log_text as repair_text


def repair_remote(month: str, vault: str | None) -> int:
    """SSH to OBSIDIAN_SERVER and repair logs in place (does not touch local vault)."""
    import os
    import shlex
    import subprocess

    server = os.environ.get("OBSIDIAN_SERVER", "obsidian-server")
    remote_vault = vault or os.environ.get("SERVER_VAULT", "/root/obsidian-vault")
    agent = os.environ.get("OBSIDIAN_AGENT_DIR", "/root/bots")
    month_arg = f" --month {shlex.quote(month)}" if month else ""
    vault_arg = f" --vault {shlex.quote(remote_vault)}"
    cmd = (
        f"cd {shlex.quote(agent)} && "
        f"python3 planning_bot/tools/repair_action_log_format.py{vault_arg}{month_arg}"
    )
    ssh = ["ssh", server, cmd]
    print("remote:", " ".join(ssh))
    return subprocess.run(ssh, check=False).returncode


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
        help="After LOCAL repair, rsync file(s) to server (overwrites server copy — use only if Mac is source of truth)",
    )
    ap.add_argument(
        "--remote",
        action="store_true",
        help="Repair on VPS via SSH (in-place on SERVER_VAULT; does not read/write local Mac logs)",
    )
    args = ap.parse_args()

    if args.remote:
        vault = str(args.vault.expanduser()) if args.vault else None
        return repair_remote(args.month, vault)

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
