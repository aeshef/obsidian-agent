#!/usr/bin/env python3
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

"""
График завершённых задач по категориям по неделям.

Данные: приоритет — SoC (completed_tasks_soc.json), fallback — общий парсер логов действий.
Пути: config.LOGS_DIR, config.GRAPHICS_DIR, config.COMPLETED_SOC_FILE.
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# Скрипт в scripts/, парсер в planning_bot/
from planning_bot.services.action_log_parser import (
    collect_events_from_logs,
    get_completion_events,
)


def week_start(dt: datetime) -> datetime:
    days_since_monday = dt.weekday()
    return (dt - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)


def _valid_category(cat) -> bool:
    """Участвует в графике только при наличии категории (тег #цель/). «Другое»/пусто не показываем."""
    c = (cat or "").strip()
    return bool(c and c != "другое")


def _completions_from_soc(soc_path: Path) -> tuple[list[dict], int]:
    """Список { dt, category } из SoC (только с completed_at и с категорией). Возвращает (completions, skipped_no_category)."""
    if not soc_path.exists():
        return [], 0
    try:
        data = json.loads(soc_path.read_text(encoding="utf-8"))
    except Exception:
        return [], 0
    entries = data.get("entries") or []
    out = []
    skipped = 0
    for e in entries:
        at = e.get("completed_at")
        if not at:
            continue
        cat = (e.get("category") or "").strip() or None
        if not _valid_category(cat):
            skipped += 1
            continue
        try:
            dt = datetime.strptime(at, "%Y-%m-%d").replace(hour=12, minute=0, second=0, microsecond=0)
        except Exception:
            continue
        out.append({"dt": dt, "category": cat})
    return out, skipped


def _completions_from_logs(events: list[dict]) -> tuple[list[dict], int]:
    """Список { dt, category } из событий логов (парсер уже отфильтровал пачки и дедуп по задаче)."""
    by_id = {}
    by_title = {}
    for e in events:
        if e.get("type") != "task_created":
            continue
        d = e.get("data") or {}
        cat = d.get("category") or ""
        if not cat:
            continue
        cat = cat.strip()
        tid = d.get("task_id")
        title = (d.get("title") or "").strip()
        if tid:
            by_id[tid] = cat
        if title:
            by_title[title] = cat

    def get_cat(d):
        tid = d.get("task_id")
        title = (d.get("title") or "").strip()
        if tid and tid in by_id:
            return by_id[tid]
        if title and title in by_title:
            return by_title[title]
        return None  # без категории — не попадёт в график

    completion_events = get_completion_events(
        events,
        filter_batch=True,
        batch_minute_threshold=5,
        dedup_per_task=True,
    )
    out = []
    skipped = 0
    for e in completion_events:
        cat = get_cat(e.get("data") or {})
        if not _valid_category(cat):
            skipped += 1
            continue
        out.append({"dt": e["dt"], "category": cat})
    return out, skipped


def aggregate_by_week_and_category(completions: list[dict]) -> tuple[list[datetime], list[str], dict[str, list[int]]]:
    week_counts = defaultdict(lambda: defaultdict(int))
    for c in completions:
        w = week_start(c["dt"])
        week_counts[w][c["category"]] += 1

    sorted_weeks = sorted(week_counts.keys())
    all_cats = set()
    for w in sorted_weeks:
        all_cats.update(week_counts[w].keys())
    category_order = [
        "карьера", "учеба", "развитие", "дом", "семья",
        "здоровье", "инфраструктура", "опыт",
    ]
    sorted_categories = [c for c in category_order if c in all_cats]
    sorted_categories += sorted(all_cats - set(sorted_categories))

    series = {cat: [week_counts[w].get(cat, 0) for w in sorted_weeks] for cat in sorted_categories}
    return sorted_weeks, sorted_categories, series


def aggregate_by_day_and_category(
    completions: list[dict],
    max_days: int = 60,
) -> tuple[list[datetime], list[str], dict[str, list[int]]]:
    """Агрегация по дням за последние max_days дней."""
    day_counts = defaultdict(lambda: defaultdict(int))
    for c in completions:
        d = c["dt"].replace(hour=0, minute=0, second=0, microsecond=0)
        day_counts[d][c["category"]] += 1

    sorted_days = sorted(day_counts.keys())
    if sorted_days:
        cutoff = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=max_days))
        sorted_days = [d for d in sorted_days if d >= cutoff]
    all_cats = set()
    for d in sorted_days:
        all_cats.update(day_counts[d].keys())
    category_order = [
        "карьера", "учеба", "развитие", "дом", "семья",
        "здоровье", "инфраструктура", "опыт",
    ]
    sorted_categories = [c for c in category_order if c in all_cats]
    sorted_categories += sorted(all_cats - set(sorted_categories))
    series = {cat: [day_counts[d].get(cat, 0) for d in sorted_days] for cat in sorted_categories}
    return sorted_days, sorted_categories, series


def build_chart_png(
    x_values: list[datetime],
    categories: list[str],
    series: dict[str, list[int]],
    out_path: Path,
    *,
    title: str = "Завершённые задачи по категориям (по неделям)",
    xlabel: str = "Неделя (Пн)",
    x_fmt: str = "%d.%m",
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(x_values)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = list(range(n))
    colors = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ]
    for i, cat in enumerate(categories):
        vals = series.get(cat, [0] * n)
        ax.plot(x, vals, marker="o", markersize=3, linewidth=1.5, label=cat, color=colors[i % len(colors)])

    ax.set_xticks(x)
    ax.set_xticklabels([t.strftime(x_fmt) for t in x_values], rotation=45, ha="right", fontsize=7 if n > 20 else 9)
    ax.set_ylabel("Завершённых задач")
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    ax.legend(loc="upper left", framealpha=0.9, fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close()


def _paths(args) -> tuple[Path, Path, Path]:
    if args.vault is not None:
        vault = Path(args.vault).resolve()
        logs_dir = vault / "300_Дашборды" / "Логи"
        out_dir = args.out_dir or (vault / "300_Дашборды" / "Графики")
        soc_path = out_dir / "completed_tasks_soc.json"
    else:
        try:
            from planning_bot.core.config import LOGS_DIR, ACTION_LOGS_DIR, GRAPHICS_DIR, COMPLETED_SOC_FILE
            logs_dir = Path(ACTION_LOGS_DIR)
            out_dir = args.out_dir or Path(GRAPHICS_DIR)
            soc_path = Path(COMPLETED_SOC_FILE)
        except Exception:
            vault = Path(__file__).resolve().parent.parent.parent.parent
            logs_dir = vault / "300_Дашборды" / "Логи"
            out_dir = args.out_dir or (vault / "300_Дашборды" / "Графики")
            soc_path = out_dir / "completed_tasks_soc.json"
    return logs_dir, out_dir, soc_path


def main():
    p = argparse.ArgumentParser(description="График завершённых задач по категориям")
    p.add_argument("--vault", type=Path, default=None)
    p.add_argument("--out-dir", type=Path, default=None)
    args = p.parse_args()

    logs_dir, out_dir, soc_path = _paths(args)
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / "Завершенные_по_категориям.png"
    md_path = out_dir / "Завершенные_по_категориям.md"
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    completions, skipped_no_cat = _completions_from_soc(soc_path)
    source = "SoC"
    if not completions:
        events = collect_events_from_logs(logs_dir)
        completions, skipped_no_cat = _completions_from_logs(events)
        source = "логи"

    if not completions:
        md_path.write_text(
            "Нет данных (SoC пуст и в логах нет завершений с категорией). Сначала: `python scripts/sync_completed_soc.py`.\n\n"
            f"Обновлено: {updated_at}\n",
            encoding="utf-8",
        )
        print(f"Записано: {md_path} (данных нет)")
        return

    weeks, categories, series = aggregate_by_week_and_category(completions)
    total = sum(series[cat][i] for cat in categories for i in range(len(weeks)))
    build_chart_png(weeks, categories, series, png_path)

    png_days_path = out_dir / "Завершенные_по_категориям_дни.png"
    days_vals, days_cats, days_series = aggregate_by_day_and_category(completions, max_days=60)
    if days_vals:
        build_chart_png(
            days_vals,
            days_cats,
            days_series,
            png_days_path,
            title="Завершённые задачи по категориям (по дням)",
            xlabel="День",
            x_fmt="%d.%m",
        )

    note_skip = f" Задач без тега #цель/ (не показаны): {skipped_no_cat}." if skipped_no_cat else ""
    body = (
        f"Учтено **{total}** завершённых задач с категорией (источник: {source}).{note_skip}\n\n"
        "**По неделям:**\n\n![График по неделям](Завершенные_по_категориям.png)\n\n"
    )
    if days_vals:
        body += "**По дням (последние 60 дней):**\n\n![График по дням](Завершенные_по_категориям_дни.png)\n\n"
    body += f"_Обновлено: {updated_at}_\n"
    md_path.write_text(body, encoding="utf-8")
    print(f"Записано: {png_path}, {png_days_path}, {md_path} (всего: {total}, без категории: {skipped_no_cat}, источник: {source})")


if __name__ == "__main__":
    main()
