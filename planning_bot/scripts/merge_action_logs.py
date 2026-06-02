#!/usr/bin/env python3
from planning_bot.core.pdmsg import pdmsg
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

pdmsg("auto_cda40eda88")
import argparse
import json
from pathlib import Path

# (comment)
import sys
from planning_bot.services.action_log_parser import parse_log_content

LOG_PREFIX = pdmsg("auto_ee3219e98d")
MONTH_NAMES = ("", "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December")


def event_key(e: dict) -> tuple:
    'Operation implementation.'
    data = e.get("data") or {}
    try:
        data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
    except Exception:
        data_str = str(data)
    return (e["timestamp"], e.get("type", "").strip(), data_str)


def write_log_file(path: Path, events: list, year_month: str) -> None:
    'Operation implementation.'
    if not events:
        return
    # (comment)
    y, m = year_month.split("-")
    month_title = f"{MONTH_NAMES[int(m)]} {y}"
    lines = [pdmsg("auto_31eabb5043", _p1=month_title)]
    for e in events:
        ts = e["timestamp"]
        typ = e.get("type", "")
        data = e.get("data") or {}
        try:
            data_json = json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            data_json = "{}"
        lines.append(f"## {ts}\n\n")
        lines.append(pdmsg("auto_f68669948a", _p1=typ))
        lines.append(pdmsg("auto_6553160aec"))
        lines.append(data_json)
        lines.append("\n```\n\n---\n\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def merge_month(dash: Path, year_month: str, dry_run: bool = False) -> tuple[int, int]:
    'Operation implementation.'
    name = f"{LOG_PREFIX}{year_month}.md"
    root_file = dash / name
    logs_dir = dash / pdmsg("auto_bcc4709278")
    out_file = logs_dir / name

    events_from_root = []
    if root_file.exists():
        try:
            events_from_root = parse_log_content(root_file.read_text(encoding="utf-8"))
        except Exception as ex:
            print(pdmsg("auto_1c5bcdbfbc", _p1=root_file, _p3=ex), flush=True)

    events_from_logs = []
    if out_file.exists():
        try:
            events_from_logs = parse_log_content(out_file.read_text(encoding="utf-8"))
        except Exception as ex:
            print(pdmsg("auto_1c5bcdbfbc", _p1=out_file, _p3=ex), flush=True)

    all_events = events_from_root + events_from_logs
    total = len(all_events)
    if not all_events:
        return 0, 0

    # (comment)
    seen = set()
    merged = []
    for e in sorted(all_events, key=lambda x: x["dt"]):
        k = event_key(e)
        if k in seen:
            continue
        seen.add(k)
        merged.append(e)

    if dry_run:
        print(pdmsg("auto_1586e06edc", _p1=year_month, _p3=total, _p5=len(merged)), flush=True)
        return total, len(merged)

    write_log_file(out_file, merged, year_month)
    if root_file.exists():
        root_file.unlink()
        print(pdmsg("auto_7febd7379d", _p1=year_month, _p3=total, _p5=len(merged), _p7=out_file), flush=True)
    else:
        print(pdmsg("auto_c7006e9059", _p1=year_month, _p3=total, _p5=len(merged), _p7=out_file), flush=True)
    return total, len(merged)


def main():
    ap = argparse.ArgumentParser(description=pdmsg("auto_cb488f816a"))
    ap.add_argument("--vault", type=Path, default=None, help=pdmsg("auto_99fde1f766"))
    ap.add_argument("--month", type=str, default=None, help=pdmsg("auto_07e5ddc10d"))
    ap.add_argument("--dry-run", action="store_true", help=pdmsg("auto_c3ff3f87d0"))
    args = ap.parse_args()

    if args.vault:
        dash = Path(args.vault) / pdmsg("auto_1c7277d3a5")
    else:
        from planning_bot.core.config import LOGS_DIR
        dash = LOGS_DIR  # (comment)

    if not dash.is_dir():
        print(pdmsg("auto_a9cfe5780b", _p1=dash), flush=True)
        return 1

    logs_dir = dash / pdmsg("auto_bcc4709278")
    if args.month:
        months = [args.month]
    else:
        # (comment)
        names = set()
        for d in (logs_dir, dash):
            if not d.exists() or not d.is_dir():
                continue
            for f in d.glob(f"{LOG_PREFIX}*.md"):
                stem = f.stem  # (comment)
                if stem.startswith(LOG_PREFIX):
                    names.add(stem[len(LOG_PREFIX):])
        months = sorted(names) if names else []

    if not months:
        print(pdmsg("auto_97dfb4f966"), flush=True)
        return 0

    total_before, total_after = 0, 0
    for ym in months:
        a, b = merge_month(dash, ym, dry_run=args.dry_run)
        total_before += a
        total_after += b

    if not args.dry_run and total_after:
        print(pdmsg("auto_31860f67b5", _p1=total_before, _p3=total_after), flush=True)
    return 0


if __name__ == "__main__":
    exit(main())
