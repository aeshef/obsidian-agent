#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent
if str(_PKG.parent) not in sys.path:
    sys.path.insert(0, str(_PKG.parent))
from planning_bot.core.pdmsg import pdmsg

from planning_bot.core.config import CONTEXT_MAC_DIR, IPHONE_CONTEXT_DIR
from planning_bot.services.action_snapshot_rename import (
    rename_snapshot_dir,
    vault_root_from_actions_dir,
    write_combined_manifest,
)
from planning_bot.services.context_parser import parse_context_file
from planning_bot.services.iphone_context_parser import parse_iphone_file
from planning_bot.services.iphone_snapshot_names import parse_filename_ts


def _resolve_ts_iphone(path: Path) -> datetime | None:
    snap = parse_iphone_file(path)
    if snap and snap.get("ts"):
        try:
            return datetime.fromisoformat(str(snap["ts"]))
        except ValueError:
            pass
    return parse_filename_ts(path.name)


def _resolve_ts_mac(path: Path) -> datetime | None:
    snaps = parse_context_file(path)
    if snaps:
        try:
            return datetime.fromisoformat(str(snaps[0]["ts"]))
        except ValueError:
            pass
    return parse_filename_ts(path.name)


def main() -> int:
    ap = argparse.ArgumentParser(description="Rename IPhone/Mac snapshot files for sortable names")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--vault", type=str, default="")
    ap.add_argument("--sync-dir", type=str, default="")
    ap.add_argument(
        "--target",
        choices=("iphone", "mac", "both"),
        default="both",
        help=pdmsg("auto_724c437831"),
    )
    ap.add_argument("--verbose", action="store_true", help=pdmsg("auto_408a9152e4"))
    ap.add_argument("--limit", type=int, default=0, help=pdmsg("auto_25cfcbabfe"))
    args = ap.parse_args()

    if args.vault:
        os.environ["VAULT_PATH"] = args.vault

    targets: list[tuple[str, Path, object]] = []
    if args.target in ("iphone", "both"):
        targets.append(("iphone", IPHONE_CONTEXT_DIR.resolve(), _resolve_ts_iphone))
    if args.target in ("mac", "both"):
        targets.append(("mac", CONTEXT_MAC_DIR.resolve(), _resolve_ts_mac))

    vault = (
        Path(args.vault).expanduser().resolve()
        if args.vault
        else vault_root_from_actions_dir(targets[0][1])
    )
    sync_dir = Path(args.sync_dir or os.environ.get("SYNC_STATE_DIR", "")).expanduser()
    if not sync_dir.is_dir():
        sync_dir = vault / ".sync"

    results = []
    for label, snap_dir, resolver in targets:
        print(f"\n=== {label}: {snap_dir} ===")
        if args.limit:
            # (comment)
            pass
        r = rename_snapshot_dir(
            snapshot_dir=snap_dir,
            vault=vault,
            resolve_ts=resolver,
            apply=args.apply,
            label=label,
            verbose=args.verbose,
        )
        print(
            pdmsg("auto_326f701285", _p1=label, _p3=r['renamed'], _p5=r['removed'], _p7=len(r['errors']))
        )
        if r.get("errors") and len(r["errors"]) <= 20:
            for e in r["errors"]:
                print(f"  ! {e}")
        elif r.get("errors"):
            print(pdmsg("auto_a871c05054", _p1=len(r['errors'])))
            for e in r["errors"][:5]:
                print(f"    {e}")
        results.append(r)

    manifest = write_combined_manifest(sync_dir, vault=vault, results=results, apply=args.apply)
    print(pdmsg("auto_d726484e0e", manifest={manifest}))
    total_unlink = sum(len(r.get("unlink_on_server") or []) for r in results)
    if args.apply and total_unlink:
        print(pdmsg("auto_5f0d40ec34", total_unlink={total_unlink}))

    ok = all(r.get("ok", True) for r in results)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
