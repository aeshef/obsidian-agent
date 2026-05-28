#!/usr/bin/env python3
from planning_bot.core.pdmsg import pdmsg
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
import re


def _discover_vault(start: Path) -> Path:
    'Operation implementation.'
    for p in [start] + list(start.parents):
        if (p / pdmsg("auto_0785c86cb9")).exists() and (p / pdmsg("auto_1c7277d3a5")).exists():
            return p
    # (comment)
    return start.parents[3]


def _paths(args) -> tuple[Path, Path]:
    if args.vault is not None:
        vault = Path(args.vault).resolve()
    else:
        vault = _discover_vault(Path(__file__).resolve())
    logs_dir = vault / pdmsg("auto_1c7277d3a5")
    action_logs_dir = logs_dir / pdmsg("auto_bcc4709278")
    out_dir = args.out_dir or (logs_dir / pdmsg("auto_1f4101e6f4"))
    return logs_dir, action_logs_dir, out_dir


def _iter_days(d0: date, d1: date) -> list[date]:
    days = []
    cur = d0
    while cur <= d1:
        days.append(cur)
        cur += timedelta(days=1)
    return days


def _load_kanban_priority_index(vault: Path) -> tuple[dict[str, str], dict[str, str], set[str]]:
    'Operation implementation.'
    kanban_path = vault / pdmsg("auto_0785c86cb9") / pdmsg("auto_1f311a1964")
    if not kanban_path.exists():
        return {}, {}, set()

    text = kanban_path.read_text(encoding="utf-8", errors="replace")
    prio_by_id: dict[str, str] = {}
    prio_by_title: dict[str, str] = {}
    active_ids: set[str] = set()

    task_pattern = r"- \[[ x]\] (.+?)(?=\n- \[|$)"
    for m in re.finditer(task_pattern, text, re.DOTALL):
        task_text = m.group(1).strip()
        title_line = task_text.splitlines()[0].strip() if task_text else ""
        title = title_line.strip()

        priority_match = re.search(pdmsg("auto_a1fb4d656a"), task_text)
        id_match = re.search(r"🆔 ID:\s*([a-f0-9-]{6,})", task_text, re.IGNORECASE)

        pr = priority_match.group(1).strip() if priority_match else ""
        tid = id_match.group(1).strip() if id_match else ""
        if tid:
            active_ids.add(tid)
        if not pr:
            continue
        if tid:
            prio_by_id[tid] = pr
        if title:
            prio_by_title[title] = pr

    return prio_by_id, prio_by_title, active_ids


def main() -> None:
    p = argparse.ArgumentParser(description=pdmsg("auto_eb9adf78be"))
    p.add_argument("--vault", type=Path, default=None)
    p.add_argument("--out-dir", type=Path, default=None)
    args = p.parse_args()

    logs_dir, action_logs_dir, out_dir = _paths(args)
    vault = Path(args.vault).resolve() if args.vault is not None else _discover_vault(Path(__file__).resolve())
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / pdmsg("auto_2ce6c30bbb")
    md_path = out_dir / pdmsg("auto_c35a11643f")

    # (comment)
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from planning_bot.services.action_log_parser import collect_events_from_logs

    events = collect_events_from_logs(action_logs_dir)
    stable_any = [e for e in events if (e.get("data") or {}).get("task_id")]
    if stable_any:
        start_dt = min(e["dt"] for e in stable_any)
    else:
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        md_path.write_text(
            pdmsg("auto_d3584c2c1a", _p1=updated_at),
            encoding="utf-8",
        )
        print(pdmsg("auto_d0388c87f5", _p1=md_path))
        return

    start_day = start_dt.date()
    end_day = datetime.now().date()
    days = _iter_days(start_day, end_day)

    # (comment)
    type_counts: dict[str, Counter] = {
        "task_created": Counter(),
        "task_moved": Counter(),
        "task_completed": Counter(),
    }

    prio_by_id, prio_by_title, active_task_ids = _load_kanban_priority_index(vault)
    moved_task_ids = {
        str((e.get("data") or {}).get("task_id"))
        for e in events
        if e.get("type") == "task_moved" and (e.get("data") or {}).get("task_id")
    }
    deleted_task_ids = moved_task_ids - active_task_ids

    # (comment)
    prio_counts: dict[str, Counter] = {
        pdmsg("auto_3520ab2a19"): Counter(),
        pdmsg("auto_16916c0f4c"): Counter(),
        pdmsg("auto_d821e337dd"): Counter(),
        pdmsg("auto_13d6c8eea4"): Counter(),
        pdmsg("auto_84649c1ec7"): Counter(),
    }

    def _get_prio(d: dict) -> str:
        pr = (d.get("priority") or "").strip()
        if pr in (pdmsg("auto_3520ab2a19"), pdmsg("auto_16916c0f4c"), pdmsg("auto_d821e337dd")):
            return pr
        tid = d.get("task_id")
        if tid and str(tid) in prio_by_id:
            return prio_by_id[str(tid)]
        if tid and str(tid) in deleted_task_ids:
            return pdmsg("auto_13d6c8eea4")
        title = (d.get("title") or "").strip()
        if title and title in prio_by_title:
            return prio_by_title[title]
        return pdmsg("auto_84649c1ec7")

    for e in events:
        d = e["dt"].date()
        if d < start_day:
            continue
        typ = e.get("type")
        if typ in type_counts:
            type_counts[typ][d] += 1

        if typ in ("task_created", "task_moved", "task_completed"):
            pr = _get_prio(e.get("data") or {})
            prio_counts[pr][d] += 1

    # (comment)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x = list(range(len(days)))
    x_labels = [d.strftime("%d.%m") for d in days]

    fig, (ax1, ax2) = plt.subplots(nrows=2, ncols=1, figsize=(12, 7.2), sharex=True)
    from matplotlib.ticker import MaxNLocator

    # (comment)
    type_labels = {
        "task_created": pdmsg("auto_a59c33b98b"),
        "task_moved": pdmsg("auto_bfa1a61232"),
        "task_completed": pdmsg("auto_65f0a19bbc"),
    }
    type_colors = {
        "task_created": "#1f77b4",
        "task_moved": "#ff7f0e",
        "task_completed": "#2ca02c",
    }
    for typ in ["task_created", "task_moved", "task_completed"]:
        y = [type_counts[typ].get(d, 0) for d in days]
        ax1.plot(x, y, marker="o", markersize=2.5, linewidth=1.4, label=type_labels[typ], color=type_colors[typ])
    ax1.set_title(pdmsg("auto_3813f80a11"))
    ax1.set_ylabel(pdmsg("auto_fb7e9a26a9"))
    ax1.grid(True, alpha=0.25)
    ax1.legend(loc="upper left", framealpha=0.9)
    ax1.set_ylim(bottom=0)
    ax1.yaxis.set_major_locator(MaxNLocator(integer=True))

    # panel 2: priority (activity)
    prio_colors = {
        pdmsg("auto_3520ab2a19"): "#d62728",
        pdmsg("auto_16916c0f4c"): "#9467bd",
        pdmsg("auto_d821e337dd"): "#7f7f7f",
        pdmsg("auto_13d6c8eea4"): "#17becf",
        pdmsg("auto_84649c1ec7"): "#bcbd22",
    }
    for pr in [pdmsg("auto_3520ab2a19"), pdmsg("auto_16916c0f4c"), pdmsg("auto_d821e337dd"), pdmsg("auto_13d6c8eea4"), pdmsg("auto_84649c1ec7")]:
        y = [prio_counts[pr].get(d, 0) for d in days]
        ax2.plot(x, y, marker="o", markersize=2.5, linewidth=1.4, label=pr, color=prio_colors[pr])
    ax2.set_title(pdmsg("auto_30046e92e3"))
    ax2.set_ylabel(pdmsg("auto_fb7e9a26a9"))
    ax2.grid(True, alpha=0.25)
    ax2.legend(loc="upper left", framealpha=0.9)
    ax2.set_ylim(bottom=0)
    ax2.yaxis.set_major_locator(MaxNLocator(integer=True))

    ax2.set_xticks(x)
    ax2.set_xticklabels(x_labels, rotation=45, ha="right", fontsize=7 if len(days) > 25 else 9)
    ax2.set_xlabel(pdmsg("auto_67bb82cf89", _p1=start_day.strftime('%Y-%m-%d')))

    fig.tight_layout()
    fig.savefig(png_path, dpi=130, bbox_inches="tight")
    plt.close(fig)

    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    md_path.write_text(
        pdmsg("auto_6df97175ce", _p1=updated_at),
        encoding="utf-8",
    )
    print(pdmsg("auto_5b2d10d70b", _p1=png_path, _p3=md_path, _p5=len(days), _p7=start_day))


if __name__ == "__main__":
    main()

