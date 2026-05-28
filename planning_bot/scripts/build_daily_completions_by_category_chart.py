#!/usr/bin/env python3
from planning_bot.core.pdmsg import pdmsg
import argparse
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
import re
from typing import Optional


def _discover_vault(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / pdmsg("auto_0785c86cb9")).exists() and (p / pdmsg("auto_1c7277d3a5")).exists():
            return p
    return start.parents[3]


def _paths(args) -> tuple[Path, Path]:
    vault = Path(args.vault).resolve() if args.vault is not None else _discover_vault(Path(__file__).resolve())
    logs_dir = vault / pdmsg("auto_1c7277d3a5")
    action_logs_dir = logs_dir / pdmsg("auto_bcc4709278")
    out_dir = args.out_dir or (logs_dir / pdmsg("auto_1f4101e6f4"))
    return logs_dir, action_logs_dir, out_dir


def _iter_days(d0: date, d1: date) -> list[date]:
    out = []
    cur = d0
    while cur <= d1:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def _load_kanban_category_index(vault: Path):
    'Operation implementation.'
    kanban_path = vault / pdmsg("auto_0785c86cb9") / pdmsg("auto_1f311a1964")
    if not kanban_path.exists():
        return {}, {}

    text = kanban_path.read_text(encoding="utf-8", errors="replace")
    cat_by_id: dict[str, str] = {}
    cat_by_title: dict[str, str] = {}

    task_pattern = r"- \[[ x]\] (.+?)(?=\n- \[|$)"
    for m in re.finditer(task_pattern, text, re.DOTALL):
        task_text = m.group(1).strip()
        title_line = task_text.splitlines()[0].strip() if task_text else ""
        title = title_line.strip()

        category_match = re.search(pdmsg("auto_8d7e383ebe"), task_text)
        id_match = re.search(r"🆔 ID:\s*([a-f0-9-]{6,})", task_text, re.IGNORECASE)

        cat = category_match.group(1).strip() if category_match else ""
        tid = id_match.group(1).strip() if id_match else ""
        if not cat:
            continue
        if tid:
            cat_by_id[tid] = cat
        if title:
            cat_by_title[title] = cat

    return cat_by_id, cat_by_title


def main() -> None:
    p = argparse.ArgumentParser(description=pdmsg("auto_e8b081156a"))
    p.add_argument("--vault", type=Path, default=None)
    p.add_argument("--out-dir", type=Path, default=None)
    args = p.parse_args()

    logs_dir, action_logs_dir, out_dir = _paths(args)
    vault = Path(args.vault).resolve() if args.vault is not None else _discover_vault(Path(__file__).resolve())
    out_dir.mkdir(parents=True, exist_ok=True)

    png_path = out_dir / pdmsg("auto_630d75801e")
    md_path = out_dir / pdmsg("auto_bb65b56717")

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from planning_bot.services.action_log_parser import collect_events_from_logs

    events = collect_events_from_logs(action_logs_dir)
    stable_any = [e for e in events if (e.get("data") or {}).get("task_id")]
    if not stable_any:
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        md_path.write_text(
            pdmsg("auto_d3584c2c1a", _p1=updated_at),
            encoding="utf-8",
        )
        print(pdmsg("auto_d0388c87f5", _p1=md_path))
        return

    start_day = min(e["dt"] for e in stable_any).date()
    end_day = datetime.now().date()
    days = _iter_days(start_day, end_day)

    # category index:
    # 1) from kanban board (most reliable, because categories exist there for all tasks)
    # (comment)
    cat_by_id, cat_by_title = _load_kanban_category_index(vault)
    for e in events:
        if e.get("type") != "task_created":
            continue
        d = e.get("data") or {}
        cat = (d.get("category") or "").strip()
        title = (d.get("title") or "").strip()
        tid = d.get("task_id")
        if not cat:
            continue
        if tid and str(tid) not in cat_by_id:
            cat_by_id[str(tid)] = cat
        if title and title not in cat_by_title:
            cat_by_title[title] = cat

    def _get_cat(d: dict) -> Optional[str]:
        cat = (d.get("category") or "").strip()
        if cat:
            return cat
        tid = d.get("task_id")
        if tid and str(tid) in cat_by_id:
            return cat_by_id[str(tid)]
        title = (d.get("title") or "").strip()
        if title and title in cat_by_title:
            return cat_by_title[title]
        return None

    # (comment)
    categories_order = [
        pdmsg("auto_c9691441d3"), pdmsg("auto_96001db447"), pdmsg("auto_388c7d6edd"), pdmsg("auto_aff66fb77a"), pdmsg("auto_98abdac51a"),
        pdmsg("auto_1c1e363097"), pdmsg("auto_a0a35957f0"), pdmsg("auto_8a59ef2159"),
    ]

    counts: dict[str, Counter] = defaultdict(Counter)  # cat -> day -> n
    skipped = 0
    for e in events:
        if e.get("type") != "task_completed":
            continue
        dday = e["dt"].date()
        if dday < start_day:
            continue
        d = e.get("data") or {}
        cat = _get_cat(d)
        if not cat:
            skipped += 1
            continue
        counts[cat][dday] += 1

    if not counts:
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        md_path.write_text(
            pdmsg("auto_d49528ed48", _p1=updated_at),
            encoding="utf-8",
        )
        print(pdmsg("auto_d0388c87f5", _p1=md_path))
        return

    all_cats = set(counts.keys())
    # (comment)
    sorted_cats = [c for c in categories_order if c in all_cats]
    for c in sorted(all_cats):
        if c not in sorted_cats:
            sorted_cats.append(c)
    if not sorted_cats:
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        md_path.write_text(
            pdmsg("auto_3b3be71533", _p1=updated_at, _p3=skipped),
            encoding="utf-8",
        )
        print(pdmsg("auto_f7b5fc7eda", _p1=md_path))
        return

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    import numpy as np

    x = np.arange(len(days))
    x_labels = [d.strftime("%d.%m") for d in days]
    width = 0.75
    fig, ax = plt.subplots(figsize=(max(10, min(len(days) * 0.4, 24)), 6))

    palette = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ]
    bottom = np.zeros(len(days))
    for i, cat in enumerate(sorted_cats):
        y = np.array([counts[cat].get(d, 0) for d in days])
        color = palette[i % len(palette)]
        total = int(y.sum())
        label = f"{cat} ({total})"
        ax.bar(x, y, width, bottom=bottom, label=label, color=color, edgecolor="white", linewidth=0.5)
        bottom = bottom + y

    ax.set_title(pdmsg("auto_8dd54c67eb"))
    ax.set_ylabel(pdmsg("auto_981ac4d96c"))
    ax.set_xlabel(pdmsg("auto_67bb82cf89", _p1=start_day.strftime('%Y-%m-%d')))
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
    ax.set_xticklabels(x_labels, rotation=45, ha="right", fontsize=8 if len(days) > 20 else 9)

    fig.tight_layout(rect=(0, 0, 0.78, 1))
    fig.savefig(png_path, dpi=130, bbox_inches="tight")
    plt.close(fig)

    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    md_path.write_text(
        pdmsg("auto_3ee371495b", _p1=updated_at, _p3=skipped),
        encoding="utf-8",
    )
    print(pdmsg("auto_ebdd9825e3", _p1=png_path, _p3=md_path, _p5=len(sorted_cats), _p7=skipped))


if __name__ == "__main__":
    main()

