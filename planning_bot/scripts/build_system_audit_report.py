#!/usr/bin/env python3
"""Maintenance script for planning bot vault data."""
from __future__ import annotations

from planning_bot.core.config import ACTION_LOG_PREFIX, DONE_COLUMN
from planning_bot.core.pdmsg import pdmsg

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def _discover_vault(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / pdmsg("auto_0785c86cb9")).exists() and (p / pdmsg("auto_1c7277d3a5")).exists():
            return p
    return start.parents[3]


def _safe_read(path: Path, max_bytes: int = 4000) -> str:
    if not path.exists():
        return pdmsg("auto_ec1658d332")
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return pdmsg("auto_18964e6f62", _p1=e)
    if len(raw) > max_bytes:
        return raw[:max_bytes] + pdmsg("auto_b6a51df9b7", _p1=len(raw))
    return raw


def _mtime_iso(path: Path) -> str:
    if not path.exists():
        return "—"
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return "?"


def main() -> None:
    p = argparse.ArgumentParser(description=pdmsg("auto_70fbbd050e"))
    p.add_argument("--vault", type=Path, default=None)
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help=pdmsg("auto_f0eb35f14d"),
    )
    args = p.parse_args()

    vault = args.vault.resolve() if args.vault else _discover_vault(Path(__file__).resolve())
    dash = vault / pdmsg("auto_1c7277d3a5")
    out = args.out or (dash / pdmsg("auto_ab7068555f"))
    if not out.is_absolute():
        out = vault / out
    out.parent.mkdir(parents=True, exist_ok=True)

    sync_dir = Path(os.environ.get("SYNC_STATE_DIR", vault / ".sync"))
    if not sync_dir.is_dir():
        sync_dir = vault / ".sync"

    lines: list[str] = [
        pdmsg("auto_5f3adcf92b"),
        "",
        pdmsg("auto_da3d8e8365", _p1=datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        "",
        pdmsg("auto_7c6ed2eb98"),
        "",
        "---",
        "",
        pdmsg("auto_5d68ea6ce6"),
        "",
        pdmsg("auto_e68aede2a2", _p1=sync_dir),
        "",
    ]

    markers = [
        "last_sync_ok.txt",
        "daily_charts_date.txt",
        "finance_dashboard_date.txt",
        "finance_dashboard_last_ok.txt",
    ]
    for name in markers:
        path = sync_dir / name
        lines.append(f"- **`{name}`** — mtime {_mtime_iso(path)}")
        if name == "last_sync_ok.txt":
            lines.append(pdmsg("auto_2aeef4eeab", _p1=_safe_read(path, 500).strip()))
        elif path.exists():
            lines.append(pdmsg("auto_2aeef4eeab", _p1=path.read_text(encoding='utf-8', errors='replace').strip()))
        lines.append("")

    health_log = sync_dir / "health.log"
    lines.append(pdmsg("auto_4361cbfc1e"))
    lines.append("")
    lines.append("```")
    if health_log.exists():
        try:
            tail = health_log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
            lines.append("\n".join(tail) if tail else pdmsg("auto_2cdb199719"))
        except OSError as e:
            lines.append(str(e))
    else:
        lines.append(pdmsg("auto_ec1658d332"))
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(pdmsg("auto_27ff33587d"))
    lines.append("")

    kanban = vault / pdmsg("auto_0785c86cb9") / pdmsg("auto_1f311a1964")
    lines.append(pdmsg("auto_6e1b3d9af2", _p1=kanban, _p3=_mtime_iso(kanban), _p5=kanban.stat().st_size if kanban.exists() else '—'))

    ks = dash / "kanban_state.json"
    if ks.exists():
        try:
            data = json.loads(ks.read_text(encoding="utf-8"))
            n = len(data) if isinstance(data, dict) else 0
            lines.append(pdmsg("auto_cfb539ba67", _p1=n, _p3=_mtime_iso(ks)))
        except Exception as e:
            lines.append(pdmsg("auto_affcfe833c", _p1=e))
    else:
        lines.append(pdmsg("auto_8aa8bea4df"))

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(pdmsg("auto_f596df73e0"))
    lines.append("")

    agent = vault / pdmsg("auto_e7eb0224f4") / "Agent"
    sys.path.insert(0, str(agent))
    from planning_bot.services.action_log_parser import collect_events_from_logs

    logs_dir = dash / pdmsg("auto_bcc4709278")
    if logs_dir.is_dir():
        md_logs = sorted(logs_dir.glob(pdmsg("auto_4f9eed73b9")))
        lines.append(pdmsg("auto_a1946a7069", _p1=len(md_logs)))
        for f in md_logs[-6:]:
            lines.append(f"  - `{f.name}` — {_mtime_iso(f)}")
        try:
            ev = collect_events_from_logs(logs_dir)
            lines.append(pdmsg("auto_2753bba2b1", _p1=len(ev)))
        except Exception as e:
            lines.append(pdmsg("auto_8a2af899de", _p1=e))
    else:
        lines.append(pdmsg("auto_e2b7028db6"))

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(pdmsg("auto_9e49e9ba8b"))
    lines.append("")

    for rel in (
        "goals_task_mapping.json",
        pdmsg("auto_97efefad77"),
    ):
        fp = dash / rel
        lines.append(pdmsg("auto_f4e3922200", _p1=rel, _p3=_mtime_iso(fp), _p5=fp.stat().st_size if fp.exists() else '—'))

    lines.append("")
    lines.append(pdmsg("auto_e6c2510b8c"))
    lines.append("")
    gfx = dash / pdmsg("auto_1f4101e6f4")
    watch = [
        pdmsg("auto_2ce6c30bbb"),
        pdmsg("auto_630d75801e"),
        pdmsg("auto_a7eaeaeabc"),
    ]
    if gfx.is_dir():
        for w in watch:
            fp = gfx / w
            lines.append(f"- `{w}` — {_mtime_iso(fp)}")
    else:
        lines.append(pdmsg("auto_d5add81d24"))

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(pdmsg("auto_dd0051d65d"))
    lines.append("")
    for key in ("VAULT_PATH", "LOCAL_VAULT", "SYNC_STATE_DIR", "PYTHONPATH"):
        v = os.environ.get(key)
        lines.append(f"- `{key}` — {pdmsg("auto_95f57d852f") if v else pdmsg("auto_d07c3c68b2")}")
    lines.append("")
    lines.append(pdmsg("auto_abbea6bcae"))

    out.write_text("\n".join(lines), encoding="utf-8")
    print(pdmsg("auto_e85c431c3c", _p1=out))


if __name__ == "__main__":
    main()
