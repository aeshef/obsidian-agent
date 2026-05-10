#!/usr/bin/env python3
"""Maintenance script for planning bot vault data."""

from __future__ import annotations

from planning_bot.core.config import ACTION_LOG_PREFIX, DONE_COLUMN
from planning_bot.core.pdmsg import pdmsg

import argparse
import os
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable


def _discover_vault(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / pdmsg("auto_0785c86cb9")).exists() and (p / pdmsg("auto_1c7277d3a5")).exists():
            return p
    return start.parents[3]


def _paths(vault: Path, out_dir: Path | None) -> Path:
    graphics = vault / pdmsg("auto_1c7277d3a5") / pdmsg("auto_1f4101e6f4")
    out = out_dir or graphics
    return out


PNG_NAME = pdmsg("auto_a7c14af2a8")
MD_NAME = pdmsg("auto_73f5ba424f")


def _sorted_categories(keys: Iterable[str], order: dict[str, int]) -> list[str]:
    keys_set = {str(k).strip() for k in keys if str(k).strip()}
    ranked = sorted(keys_set, key=lambda c: (order.get(c, 99), c.lower()))
    return ranked


def main() -> None:
    p = argparse.ArgumentParser(description=pdmsg("auto_a4b61b85dc"))
    p.add_argument("--vault", type=Path, default=None)
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument(
        "--days",
        type=int,
        default=int(os.environ.get("DEADLINE_CHART_HORIZON_DAYS", "120")),
        help=pdmsg("auto_b6cb5a5ad5"),
    )
    args = p.parse_args()

    vault = Path(args.vault).resolve() if args.vault else _discover_vault(Path(__file__).resolve())
    os.environ["VAULT_PATH"] = str(vault)

    agent_root = Path(__file__).resolve().parent.parent.parent
    if str(agent_root) not in sys.path:
        sys.path.insert(0, str(agent_root))

    from planning_bot.core.config import CATEGORY_ORDER, DONE_COLUMN, KANBAN_COLUMNS
    from planning_bot.services.kanban import KanbanBoard

    out_dir = _paths(vault, args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / PNG_NAME
    md_path = out_dir / MD_NAME

    horizon = max(7, min(int(args.days), 366 * 3))

    open_columns = frozenset(KANBAN_COLUMNS[:-1])
    board = KanbanBoard()
    tasks = board.get_tasks(exclude_today=False, exclude_blocked=False)

    today = date.today()
    last_day = today + timedelta(days=horizon - 1)
    day_range = [today + timedelta(days=i) for i in range(horizon)]

    by_day: dict[date, Counter[str]] = {d: Counter() for d in day_range}
    overdue: Counter[str] = Counter()
    beyond = 0

    for t in tasks:
        if t.get("completed"):
            continue
        col = t.get("column")
        if col not in open_columns:
            continue
        dl_raw = (t.get("deadline") or "").strip()
        if not dl_raw:
            continue
        try:
            dl = datetime.strptime(dl_raw, "%Y-%m-%d").date()
        except ValueError:
            continue

        cat = (t.get("category") or "").strip() or pdmsg("auto_1945da1fe5")

        if dl < today:
            overdue[cat] += 1
        elif dl in by_day:
            by_day[dl][cat] += 1
        else:
            beyond += 1

    all_cats: set[str] = set(overdue.keys())
    for c in by_day.values():
        all_cats.update(c.keys())
    sorted_cats = _sorted_categories(all_cats, CATEGORY_ORDER)

    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M")
    overdue_total = int(sum(overdue.values()))
    future_total = int(sum(sum(dc.values()) for dc in by_day.values()))

    if not sorted_cats and overdue_total == 0 and future_total == 0:
        md_path.write_text(
            pdmsg("auto_c32df46433", _p1=DONE_COLUMN, _p3=now_iso),
            encoding="utf-8",
        )
        print(pdmsg("auto_1d0bd0c01c", _p1=md_path))
        return

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.ticker import MaxNLocator

    palette = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ]

    title_suffix = (
        pdmsg("auto_5941923973", _p1=overdue_total, _p3=future_total)
        + (pdmsg("auto_cae59f782b", _p1=beyond) if beyond else "")
    )

    if future_total == 0:
        fig, ax = plt.subplots(figsize=(9, 3.8))
        ax.text(
            0.5,
            0.55,
            pdmsg("auto_449f623f15"),
            ha="center",
            va="center",
            fontsize=12,
            transform=ax.transAxes,
        )
        ax.set_title(pdmsg("auto_f7a1b08720", _p1=title_suffix), fontsize=11)
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(png_path, dpi=130, bbox_inches="tight")
        plt.close(fig)
    else:
        n = len(day_range)
        x = np.arange(n)
        x_labels = [d.strftime("%d.%m") for d in day_range]

        fig_w = max(11, min(n * 0.22, 36))
        fig, ax = plt.subplots(figsize=(fig_w, 6.2))
        bottom = np.zeros(n)

        for i, cat in enumerate(sorted_cats):
            y = np.array([int(by_day[d].get(cat, 0)) for d in day_range], dtype=float)
            if y.sum() == 0:
                continue
            color = palette[i % len(palette)]
            sm = int(y.sum())
            ax.bar(
                x,
                y,
                0.92,
                bottom=bottom,
                label=f"{cat} (Σ {sm})",
                color=color,
                edgecolor="white",
                linewidth=0.45,
            )
            bottom = bottom + y

        ax.set_title(pdmsg("auto_4d8f0fd70f") + title_suffix, fontsize=11)
        ax.set_ylabel(pdmsg("auto_8c60238010"))
        ax.set_xlabel(pdmsg("auto_402d37af44"))
        ax.set_ylim(bottom=0)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        if sorted_cats and float(bottom.max()) > 0:
            ax.legend(
                loc="upper left",
                bbox_to_anchor=(1.02, 1.0),
                borderaxespad=0.0,
                framealpha=0.95,
                fontsize=8,
            )
        ax.set_xticks(x)
        rot = 60 if n > 28 else (45 if n > 16 else 0)
        ha = "right" if rot else "center"
        ax.set_xticklabels(x_labels, rotation=rot, ha=ha, fontsize=7 if n > 40 else 8)
        fig.tight_layout(rect=(0, 0, 0.78 if sorted_cats else 1, 1))
        fig.savefig(png_path, dpi=130, bbox_inches="tight")
        plt.close(fig)

    overdue_lines = []
    if overdue_total:
        overdue_lines.append(pdmsg("auto_704cc97621"))
        for cat in _sorted_categories(overdue.keys(), CATEGORY_ORDER):
            overdue_lines.append(f"- {cat}: **{overdue[cat]}**")
        overdue_lines.append("")
    elif not sorted_cats:
        pass
    else:
        overdue_lines.append(pdmsg("auto_36493c9df7"))

    note_beyond = (
        pdmsg("auto_708c565f7e", _p1=last_day.isoformat(), _p3=beyond)
        if beyond
        else ""
    )

    md_path.write_text(
        pdmsg("auto_ca50e0ca98", _p1=DONE_COLUMN, _p3=today.isoformat(), _p5=last_day.isoformat(), _p7=horizon)
        + "\n".join(overdue_lines)
        + pdmsg("auto_7ea002a857", _p1=PNG_NAME)
        + note_beyond
        + pdmsg("auto_e3dd0ca3fe", _p1=now_iso, _p3=horizon),
        encoding="utf-8",
    )
    print(
        pdmsg("auto_1d0008adcd", _p1=png_path, _p3=md_path, _p5=overdue_total, _p7=future_total, _p9=len(sorted_cats)),
    )


if __name__ == "__main__":
    main()
