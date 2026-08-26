#!/usr/bin/env python3
"""Materialize Mac context snapshots from LaunchAgent stdout into Actions/Mac/*.txt.

The Shortcuts LA often prints snapshots to /tmp/mac-context-obsidian.out but fails to
Save File into the vault (TCC / Safari branch). This recovers those records.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

_AGENT = Path(__file__).resolve().parent.parent.parent
if str(_AGENT) not in sys.path:
    sys.path.insert(0, str(_AGENT))

from planning_bot.core.config import CONTEXT_MAC_DIR
from planning_bot.services.context_parser import _parse_ts

_DEFAULT_STDOUT = Path("/tmp/mac-context-obsidian.out")
_TS_LINE = re.compile(r"(?im)^\s*ts:\s*(.+?)\s*$")


def _canonical_name(dt: datetime) -> str:
    return f"{dt.strftime('%Y-%m-%d')}, {dt.strftime('%H-%M')}.txt"


def _iter_blocks(text: str) -> list[str]:
    """Split LaunchAgent stdout into snapshot blocks (handles '---   ---' glued lines)."""
    # Normalize glued separators from Shortcuts/stdout concatenation.
    text = re.sub(r"-{3,}\s*-{3,}", "\n---\n", text)
    parts = re.split(r"(?m)^\s*-{3,}\s*$", text)
    return [p.strip() for p in parts if p and p.strip()]


def _normalize_block(raw: str) -> tuple[str, datetime] | None:
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        fields[k.strip().lower()] = v.strip()
    ts_raw = fields.get("ts")
    if not ts_raw:
        m = _TS_LINE.search(raw)
        ts_raw = m.group(1).strip() if m else ""
    if not ts_raw:
        return None
    dt = _parse_ts(ts_raw)
    if dt is None:
        return None
    # Store in the same shape the June Shortcut used (parser accepts both).
    lines = [
        "   ---",
        f"   ts: {dt.strftime('%d.%m.%Y, %H:%M')}",
        f"   source: {fields.get('source') or 'mac'}",
    ]
    for key in (
        "safari_title",
        "app",
        "wifi",
        "battery_pct",
        "focus",
        "focus_window",
        "idle_sec",
        "window_title",
    ):
        if key in fields and fields[key] != "":
            lines.append(f"   {key}: {fields[key]}")
    lines.append("   ---")
    return "\n".join(lines) + "\n", dt


def ingest(stdout_path: Path, mac_dir: Path, *, days: int = 14) -> dict:
    mac_dir.mkdir(parents=True, exist_ok=True)
    if not stdout_path.is_file():
        return {"ok": False, "reason": f"missing {stdout_path}", "written": 0, "skipped": 0}

    text = stdout_path.read_text(encoding="utf-8", errors="replace")
    written = 0
    skipped = 0
    cutoff = datetime.now().timestamp() - days * 86400
    seen: set[str] = set()

    for seg in _iter_blocks(text):
        norm = _normalize_block(seg)
        if not norm:
            continue
        body, dt = norm
        if dt.timestamp() < cutoff:
            continue
        name = _canonical_name(dt)
        # Same-minute collisions: keep first, suffix extras.
        dest = mac_dir / name
        if name in seen or dest.exists():
            if dest.exists() and name not in seen:
                skipped += 1
                seen.add(name)
                continue
            n = 2
            while True:
                alt = f"{dt.strftime('%Y-%m-%d')}, {dt.strftime('%H-%M')}_{n}.txt"
                dest = mac_dir / alt
                if alt not in seen and not dest.exists():
                    name = alt
                    break
                n += 1
        seen.add(name)
        dest.write_text(body, encoding="utf-8")
        written += 1

    return {
        "ok": True,
        "stdout": str(stdout_path),
        "mac_dir": str(mac_dir),
        "written": written,
        "skipped": skipped,
        "unique": len(seen),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--stdout",
        default=os.environ.get("MAC_CONTEXT_STDOUT", str(_DEFAULT_STDOUT)),
        help="LaunchAgent StandardOutPath (default /tmp/mac-context-obsidian.out)",
    )
    ap.add_argument("--mac-dir", default="", help="Override CONTEXT_MAC_DIR")
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args()
    mac_dir = Path(args.mac_dir).expanduser() if args.mac_dir else CONTEXT_MAC_DIR
    result = ingest(Path(args.stdout).expanduser(), mac_dir, days=args.days)
    print(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
