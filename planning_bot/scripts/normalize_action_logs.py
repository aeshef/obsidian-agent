#!/usr/bin/env python3
from planning_bot.core.pdmsg import pdmsg
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

pdmsg("auto_8c1573ec79")
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

LOG_PREFIX = pdmsg("auto_ee3219e98d")
MONTH_NAMES = ("", "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December")

from planning_bot.services.action_log_parser import parse_log_content


def first_line_only(s: str) -> str:
    'Operation implementation.'
    if not s or "\n" not in s:
        return s
    return s.split("\n")[0].strip()


def normalize_data(data: dict) -> dict:
    'Operation implementation.'
    if not isinstance(data, dict):
        return data
    out = dict(data)
    if "to" in out and isinstance(out["to"], str):
        out["to"] = first_line_only(out["to"])
    if "from" in out and isinstance(out["from"], str):
        out["from"] = first_line_only(out["from"])
    return out


def write_log_file(path: Path, events: list, year_month: str) -> None:
    'Operation implementation.'
    if not events:
        return
    y, m = year_month.split("-")
    month_title = f"{MONTH_NAMES[int(m)]} {y}"
    lines = [pdmsg("auto_31eabb5043", _p1=month_title)]
    for e in events:
        ts = e["timestamp"]
        typ = e.get("type", "")
        data = e.get("data") or {}
        data_json = json.dumps(data, ensure_ascii=False, indent=2)
        lines.append(f"## {ts}\n\n")
        lines.append(pdmsg("auto_f68669948a", _p1=typ))
        lines.append(pdmsg("auto_6553160aec"))
        lines.append(data_json)
        lines.append("\n```\n\n---\n\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=pdmsg("auto_4b3bd9bf5f"))
    ap.add_argument("--vault", type=Path, default=None)
    ap.add_argument("--month", type=str, default=None, help=pdmsg("auto_3bba8862bb"))
    ap.add_argument("--dry-run", action="store_true", help=pdmsg("auto_ac1b3fb421"))
    ap.add_argument("--push-to-server", action="store_true", help=pdmsg("auto_03a7292162"))
    args = ap.parse_args()

    if args.vault:
        logs_dir = Path(args.vault) / pdmsg("auto_1c7277d3a5") / pdmsg("auto_bcc4709278")
    else:
        from planning_bot.core.config import ACTION_LOGS_DIR
        logs_dir = Path(ACTION_LOGS_DIR)

    if not logs_dir.is_dir():
        print(pdmsg("auto_a9cfe5780b", _p1=logs_dir), flush=True)
        return 1

    if args.month:
        files = [logs_dir / f"{LOG_PREFIX}{args.month}.md"]
        files = [f for f in files if f.exists()]
    else:
        files = sorted(logs_dir.glob(f"{LOG_PREFIX}*.md"))

    if not files:
        print(pdmsg("auto_305d1caee7"), flush=True)
        return 0

    fixed_count = 0
    for path in files:
        content = path.read_text(encoding="utf-8")
        events = parse_log_content(content)
        if not events:
            continue
        year_month = path.stem.replace(LOG_PREFIX, "")
        if not year_month:
            continue
        changed = 0
        for e in events:
            data = e.get("data") or {}
            if not isinstance(data, dict):
                continue
            new_data = normalize_data(data)
            if new_data != data:
                changed += 1
            e["data"] = new_data
        if changed:
            fixed_count += changed
            if args.dry_run:
                print(pdmsg("auto_be3a11fa77", _p1=path.name, _p3=changed), flush=True)
            else:
                write_log_file(path, events, year_month)
                print(pdmsg("auto_7b67d98846", _p1=path.name, _p3=changed), flush=True)

    if fixed_count and not args.dry_run:
        print(pdmsg("auto_f5f94578f3", _p1=fixed_count), flush=True)
    elif fixed_count and args.dry_run:
        print(pdmsg("auto_9c8cf414d2", _p1=fixed_count), flush=True)
    elif not fixed_count and not args.dry_run:
        print(pdmsg("auto_411f35068d"), flush=True)

    if args.push_to_server and not args.dry_run and logs_dir.is_dir():
        server = os.environ["SERVER"]
        server_vault = os.environ.get("SERVER_VAULT", "/opt/obsidian-vault")
        rsh = os.environ.get("RSYNC_RSH", "ssh -o UseKeychain=yes -o BatchMode=yes")
        src = str(logs_dir.resolve()).rstrip("/") + "/"
        dst = pdmsg("auto_c8ebd8fb48", _p0=server, _p2=server_vault)
        cmd = ["rsync", "-avz", "-e", rsh, src, dst]
        print(pdmsg("auto_e99f342cc0", _p1=src, _p3=dst), flush=True)
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(pdmsg("auto_0ab47247bd"), flush=True)
            return 1
        print(pdmsg("auto_af6c672379"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
