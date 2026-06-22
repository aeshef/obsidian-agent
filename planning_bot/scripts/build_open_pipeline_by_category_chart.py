#!/usr/bin/env python3
"""Build open pipeline by category chart from vault data."""

from __future__ import annotations

from planning_bot.core.config import ACTION_LOG_PREFIX, DONE_COLUMN, GRAPHICS_DIR
from planning_bot.core.pdmsg import pdmsg
from planning_bot.core.vault_discover import discover_vault
from shared.vault_paths_config import vault_file

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any



def _paths(vault: Path, out_dir: Path | None) -> tuple[Path, Path]:
    graphics = vault / pdmsg("auto_1c7277d3a5") / pdmsg("auto_1f4101e6f4")
    out = out_dir or graphics
    return graphics, out


HISTORY_FILENAME = vault_file("open_tasks_history_json")
PNG_NAME = vault_file("chart_open_pipeline_png")
MD_NAME = vault_file("chart_open_pipeline_md")

def _sorted_category_keys(keys: set[str]) -> list[str]:
    from planning_bot.core.config import CATEGORIES, CATEGORY_ORDER

    order = {c: int(CATEGORY_ORDER.get(c, 99)) for c in CATEGORIES}
    out = sorted((c for c in keys if c in order), key=lambda c: order[c])
    for c in sorted(keys):
        if c not in out:
            out.append(c)
    return out


def _load_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    snaps = data.get("snapshots")
    if not isinstance(snaps, list):
        return []
    return [s for s in snaps if isinstance(s, dict) and s.get("date")]


def _save_history(path: Path, snapshots: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"snapshots": snapshots}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _wait_for_stable_file(path: Path, stable_seconds: float = 3.0, timeout_seconds: float = 20.0) -> bool:
    """Avoid taking a chart snapshot while Obsidian or the ID watcher is rewriting the board."""
    if not path.exists():
        return False
    started = time.time()
    last_mtime = path.stat().st_mtime
    stable_since = time.time()
    while time.time() - started < timeout_seconds:
        time.sleep(0.5)
        current_mtime = path.stat().st_mtime
        if current_mtime != last_mtime:
            last_mtime = current_mtime
            stable_since = time.time()
            continue
        if time.time() - stable_since >= stable_seconds:
            return True
    return False


def main() -> None:
    p = argparse.ArgumentParser(
        description=pdmsg("auto_c55ab2c2b1"),
    )
    p.add_argument("--vault", type=Path, default=None)
    p.add_argument("--out-dir", type=Path, default=None)
    args = p.parse_args()

    vault = Path(args.vault).resolve() if args.vault else discover_vault(Path(__file__).resolve())
    os.environ["VAULT_PATH"] = str(vault)

    agent_root = Path(__file__).resolve().parent.parent.parent
    if str(agent_root) not in sys.path:
        sys.path.insert(0, str(agent_root))

    from planning_bot.core.config import DONE_COLUMN, KANBAN_COLUMNS, KANBAN_FILE
    from planning_bot.services.kanban import KanbanBoard

    out_dir = Path(args.out_dir).resolve() if args.out_dir else GRAPHICS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    history_path = out_dir / HISTORY_FILENAME
    png_path = out_dir / PNG_NAME
    md_path = out_dir / MD_NAME

    open_columns = frozenset(KANBAN_COLUMNS[:-1])

    _wait_for_stable_file(KANBAN_FILE)
    board = KanbanBoard()
    tasks = board.get_tasks(exclude_today=False, exclude_blocked=False)

    by_cat: Counter[str] = Counter()
    skipped_no_column = 0
    for t in tasks:
        if t.get("completed"):
            continue
        col = t.get("column")
        if col not in open_columns:
            if col and col not in (DONE_COLUMN, pdmsg("auto_ca7b1482d8")):
                skipped_no_column += 1
            continue
        cat = (t.get("category") or "").strip() or pdmsg("auto_1945da1fe5")
        by_cat[cat] += 1

    total = int(sum(by_cat.values()))
    today_s = date.today().isoformat()
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M")

    snap = {
        "date": today_s,
        "updated_at": now_iso,
        "total": total,
        "by_category": dict(by_cat),
    }

    snapshots = _load_history(history_path)
    # (comment)
    snapshots = [s for s in snapshots if s.get("date") != today_s]
    snapshots.append(snap)
    snapshots.sort(key=lambda s: str(s.get("date", "")))
    _save_history(history_path, snapshots)

    if not snapshots:
        md_path.write_text(
            pdmsg("auto_706f8573d0", _p1=now_iso),
            encoding="utf-8",
        )
        print(pdmsg("auto_c936bb9e6f", _p1=md_path))
        return

    days = [datetime.strptime(str(s["date"]), "%Y-%m-%d").date() for s in snapshots]
    all_cats: set[str] = set()
    for s in snapshots:
        bc = s.get("by_category") or {}
        if isinstance(bc, dict):
            all_cats.update(bc.keys())

    sorted_cats = _sorted_category_keys(all_cats)
    if not sorted_cats:
        md_path.write_text(
            pdmsg("auto_e9398dd445", _p1=len(snapshots), _p3=now_iso),
            encoding="utf-8",
        )
        print(pdmsg("auto_d4de75d14b", _p1=md_path))
        return

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    import numpy as np

    n = len(days)
    x = np.arange(n)
    x_labels = [d.strftime("%d.%m") for d in days]
    width = 0.82

    palette = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ]
    fig_w = max(10, min(n * 0.55, 28))
    fig, ax = plt.subplots(figsize=(fig_w, 6))
    bottom = np.zeros(n)

    def _series(cat: str) -> np.ndarray:
        return np.array([
            int((s.get("by_category") or {}).get(cat, 0) or 0)
            for s in snapshots
        ])

    for i, cat in enumerate(sorted_cats):
        y = _series(cat)
        color = palette[i % len(palette)]
        sm = int(y.sum())
        label = f"{cat} (Σ {sm})"
        ax.bar(x, y, width, bottom=bottom, label=label, color=color, edgecolor="white", linewidth=0.5)
        bottom = bottom + y

    ax.set_title(pdmsg("auto_7df5d9ef7a"))
    ax.set_ylabel(pdmsg("auto_a0d9fab4a6"))
    ax.set_xlabel(pdmsg("auto_c40dda98e9"))
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        borderaxespad=0.0,
        framealpha=0.95,
        fontsize=9,
    )
    ax.set_xticks(x)
    rot = 45 if n > 14 else 0
    ha = "right" if rot else "center"
    ax.set_xticklabels(x_labels, rotation=rot, ha=ha, fontsize=8 if n > 20 else 9)

    fig.tight_layout(rect=(0, 0, 0.78, 1))
    fig.savefig(png_path, dpi=130, bbox_inches="tight")
    plt.close(fig)

    note_skip = pdmsg("auto_d5796e610d", _p1=skipped_no_column) if skipped_no_column else ""
    md_path.write_text(
        pdmsg("auto_2620f8935c", _p1=note_skip, _p3=total, _p5=PNG_NAME, _p7=now_iso, _p9=len(snapshots)),
        encoding="utf-8",
    )
    print(
        pdmsg("auto_2884b09c5a", _p1=png_path, _p3=md_path, _p5=history_path, _p7=total, _p9=len(sorted_cats)),
    )


if __name__ == "__main__":
    main()
