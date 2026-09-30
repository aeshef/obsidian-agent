#!/usr/bin/env python3
"""Seed a full English synthetic Obsidian vault (life OS) for product demos.

Does NOT read or modify Agent/.env or your main vault.
Always pass an explicit --vault path outside your personal vault.

  PYTHONPATH=. ./scripts/oa-python.sh scripts/seed_demo_vault.py \\
    --vault "/path/to/demo-vault-en"

Safe: synthetic titles only. No PII. No RUB / Cyrillic. Idempotent overwrite.

Run the bot without touching .env:

  cp -n .env.demo.example .env.demo
  ./scripts/run_unified_bot_demo.sh
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ~4 months of synthetic history — charts look smooth on film, not spiky/empty.
DEMO_HISTORY_DAYS = 120

# Kanban column titles (must match kanban_schema.en.yaml.example — replay breaks on short names).
COL_BACKLOG = "📋 Backlog"
COL_WAITING = "📅 Waiting for date"
COL_DEFERRED = "⏸ Deferred"
COL_IN_PROGRESS = "🔄 In progress"
COL_BLOCKED = "🚫 Blocked"
COL_DONE = "✅ Done"

OPEN_CATEGORIES = [
    "career",
    "growth",
    "infrastructure",
    "home",
    "health",
    "experience",
    "study",
]
TASKS = "100_Tasks"
GOALS = "200_Goals"
DASH = "300_Dashboards"
ROUTINES = "400_Routines"
HANDWRITTEN = "600_Handwritten"
ARCHIVE = "600_Archive"
KNOWLEDGE = "Knowledge"
LOGS = "Logs"
DATA = "Data"
NOTES = "Notes"


def _die_if_looks_like_main_vault(vault: Path) -> None:
    """Refuse obvious personal vault roots."""
    name = vault.name.lower()
    if name in {"obsidian vault", "vault"} and (vault / "800_Автоматизация" / "Agent").is_dir():
        print(
            f"Refusing to seed into likely main vault: {vault}\n"
            "Pass a dedicated folder, e.g. .../demo-vault-en",
            file=sys.stderr,
        )
        sys.exit(2)
    try:
        vault.resolve().relative_to(ROOT.resolve())
        print(f"Refusing to seed inside Agent repo: {vault}", file=sys.stderr)
        sys.exit(2)
    except ValueError:
        pass


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.lstrip("\n"), encoding="utf-8")
    print(f"  wrote {path}")


def _yesterday() -> date:
    return date.today() - timedelta(days=1)


def _mkdirs(vault: Path) -> None:
    for p in (
        vault / TASKS,
        vault / GOALS,
        vault / DASH / LOGS,
        vault / DASH / DATA / "Actions" / "IPhone",
        vault / DASH / DATA / "Actions" / "Mac",
        vault / DASH / "Charts" / "Planning",
        vault / DASH / "Charts" / "Health",
        vault / DASH / "Charts" / "Finance",
        vault / DASH / "Charts" / "Cross",
        vault / DASH / "Charts" / "Analytics",
        vault / DASH / "Charts" / "System",
        vault / ROUTINES / "📅 Routines",
        vault / ROUTINES / "📊 Signals",
        vault / ROUTINES / DATA,
        vault / ROUTINES / "Charts" / "Routines",
        vault / ROUTINES / "Charts" / "Signals",
        vault / HANDWRITTEN,
        vault / ARCHIVE,
        vault / KNOWLEDGE / NOTES,
        vault / KNOWLEDGE / "_Hubs",
        vault / KNOWLEDGE / "_Attachments",
        vault / KNOWLEDGE / "Books",
        vault / KNOWLEDGE / "Places",
        vault / KNOWLEDGE / "Ideas",
        vault / KNOWLEDGE / "Recipes",
        vault / "800_Automation",
        vault / "Agent" / "logs",
    ):
        p.mkdir(parents=True, exist_ok=True)


def _seed_kanban(vault: Path) -> None:
    """Priorities: high/low only — chart buckets are high/average/low (medium KeyErrors).

    Task IDs are 8-char hex so Main Dashboard dataview mapping regex matches.
    """
    y = _yesterday().isoformat()
    t = date.today()
    d14 = (t + timedelta(days=14)).isoformat()
    d21 = (t + timedelta(days=21)).isoformat()
    d7 = (t + timedelta(days=7)).isoformat()
    board = vault / TASKS / "📋 Task_Board.md"
    _write(
        board,
        f"""
---
kanban-plugin: board
---

## 📋 Backlog

- [ ] Plan Q4 goals workshop
	#goal/career #priority/high
	📅 Created: {t.isoformat()}
	🆔 ID: a1000001

- [ ] Read systems design notes
	#goal/growth #priority/low
	📅 Created: {t.isoformat()}
	🆔 ID: a1000002

- [ ] Outline newsletter draft
	#goal/growth #priority/low
	📅 Created: {(t - timedelta(days=1)).isoformat()}
	🆔 ID: a1000003

- [ ] Review analytics dashboard copy
	#goal/career #priority/high
	📅 Created: {(t - timedelta(days=2)).isoformat()}
	🆔 ID: a1000004

- [ ] Update dependency pins
	#goal/infrastructure #priority/high
	📅 Created: {(t - timedelta(days=4)).isoformat()}
	🆔 ID: a1000005

- [ ] Schedule user interviews
	#goal/career #priority/high
	📅 Created: {(t - timedelta(days=6)).isoformat()}
	🆔 ID: a1000006

- [ ] Clean up Knowledge hubs
	#goal/growth #priority/low
	📅 Created: {(t - timedelta(days=8)).isoformat()}
	🆔 ID: a1000007

## 📅 Waiting for date

- [ ] Renew domain registration
	#goal/infrastructure #priority/high #deadline/{d14}
	📅 Created: {(t - timedelta(days=3)).isoformat()}
	📅 {d14}
	🆔 ID: a2000001

- [ ] Book dentist checkup
	#goal/health #priority/low #deadline/{d21}
	📅 Created: {(t - timedelta(days=10)).isoformat()}
	📅 {d21}
	🆔 ID: a2000002

- [ ] Book weekend train tickets
	#goal/experience #priority/low #deadline/{d7}
	📅 Created: {(t - timedelta(days=5)).isoformat()}
	📅 {d7}
	🆔 ID: a2000003

## ⏸ Deferred

- [ ] Migrate old bookmarks
	#goal/infrastructure #priority/low
	📅 Created: {(t - timedelta(days=40)).isoformat()}
	🆔 ID: a3000001

- [ ] Reorganize archive folder
	#goal/home #priority/low
	📅 Created: {(t - timedelta(days=55)).isoformat()}
	🆔 ID: a3000002

## 🔄 In progress

- [ ] Ship demo vault seed
	#goal/career #priority/high
	📅 Created: {(t - timedelta(days=2)).isoformat()}
	🆔 ID: a4000001

- [ ] Rewrite onboarding docs
	#goal/growth #priority/high
	📅 Created: {(t - timedelta(days=5)).isoformat()}
	🆔 ID: a4000002

- [ ] Polish finance dashboard charts
	#goal/infrastructure #priority/high
	📅 Created: {(t - timedelta(days=4)).isoformat()}
	🆔 ID: a4000003

## 🚫 Blocked

- [ ] Broker API sandbox access
	#goal/infrastructure #priority/high
	📅 Created: {(t - timedelta(days=7)).isoformat()}
	🆔 ID: a5000001

## ✅ Done

- [x] Ship docs
	#goal/career #priority/high
	📅 Created: {y}
	✅ {y}
	🆔 ID: a6000001

- [x] Open issue
	#goal/career #priority/high
	📅 Created: {y}
	✅ {y}
	🆔 ID: a6000002

- [x] Fix CI badges
	#goal/infrastructure #priority/high
	📅 Created: {y}
	✅ {y}
	🆔 ID: a6000003

- [x] Draft trip plan note
	#goal/experience #priority/low
	📅 Created: {y}
	✅ {y}
	🆔 ID: a6000004

- [x] Weekly grocery run
	#goal/home #priority/low
	📅 Created: {y}
	✅ {y}
	🆔 ID: a6000005

%% kanban:settings
{{"kanban-plugin":"board"}}
%%
""",
    )


def _seed_closed_archive(vault: Path) -> None:
    """Closed tasks archive so Progress 'Done 30d / Done all' is non-empty."""
    today = date.today()
    lines = [
        "---",
        "kanban-plugin: board",
        "---",
        "",
        f"## ✅ Done · {today.strftime('%Y-%m')}",
        "",
    ]
    archive_titles = [
        ("Ship docs", "career", "high"),
        ("Open issue", "career", "high"),
        ("Fix CI badges", "infrastructure", "high"),
        ("Draft trip plan note", "experience", "low"),
        ("Weekly grocery run", "home", "low"),
        ("Review pull request", "career", "high"),
        ("Update onboarding", "growth", "high"),
        ("Pay utilities", "home", "low"),
        ("Gym session plan", "health", "low"),
        ("Refactor chart tools", "infrastructure", "high"),
        ("Write test cases", "infrastructure", "high"),
        ("Sync with design", "career", "high"),
        ("Read chapter notes", "study", "low"),
        ("Plan sprint retro", "career", "high"),
        ("Organize inbox", "home", "low"),
        ("Stretch routine", "health", "low"),
        ("Coffee with mentor", "growth", "low"),
        ("Debug flaky test", "infrastructure", "high"),
    ]
    for i in range(45):
        d = today - timedelta(days=1 + (i % 28))
        title, cat, prio = archive_titles[i % len(archive_titles)]
        tid = f"b{i:07x}"[-8:]  # 8 hex chars
        lines.append(f"- [x] {title} (archive {i+1})")
        lines.append(f"\t#goal/{cat} #priority/{prio}")
        lines.append(f"\t📅 Created: {(d - timedelta(days=2)).isoformat()}")
        lines.append(f"\t✅ {d.isoformat()}")
        lines.append(f"\t🆔 ID: {tid}")
        lines.append("")
    # Prior month section for doneAll depth
    prev = today.replace(day=1) - timedelta(days=1)
    lines.append(f"## ✅ Done · {prev.strftime('%Y-%m')}")
    lines.append("")
    for i in range(20):
        d = prev - timedelta(days=i)
        title, cat, prio = archive_titles[(i + 3) % len(archive_titles)]
        tid = f"c{i:07x}"[-8:]
        lines.append(f"- [x] {title} (older {i+1})")
        lines.append(f"\t#goal/{cat} #priority/{prio}")
        lines.append(f"\t📅 Created: {(d - timedelta(days=3)).isoformat()}")
        lines.append(f"\t✅ {d.isoformat()}")
        lines.append(f"\t🆔 ID: {tid}")
        lines.append("")
    path = vault / TASKS / "📦 Closed_Tasks.md"
    _write(path, "\n".join(lines))


def _seed_goals(vault: Path) -> None:
    year = date.today().year
    _write(
        vault / GOALS / f"🎯 {year}_Goals.md",
        f"""
# {year} Goals

## Q1

- [x] Define yearly themes #goal/growth #focus/Q1 #priority/high
- [x] Set up personal finance tracking #goal/home #focus/Q1 #priority/high
- [x] Establish morning walk habit #goal/health #focus/Q1 #priority/low

## Q2

- [x] Ship first public OSS issue set #goal/career #focus/Q2 #priority/high
- [x] Read Thinking in Systems #goal/growth #focus/Q2 #priority/low
- [x] One overnight trip #goal/experience #focus/Q2 #priority/low

## Q3

- [ ] Ship public demo of the life OS #goal/career #focus/Q3 #priority/high
- [ ] Read one systems paper a week #goal/growth #focus/Q3 #priority/low
- [ ] Keep weekly grocery budget under 200 #goal/home #focus/Q3 #priority/high
- [ ] Walk 8k steps most weekdays #goal/health #focus/Q3 #priority/low
- [ ] One weekend trip this quarter #goal/experience #focus/Q3 #priority/low
- [ ] Harden agent budget gates #goal/infrastructure #focus/Q3 #priority/high

## Q4

- [ ] Plan Q4 goals workshop #goal/career #focus/Q4 #priority/high
- [ ] Publish demo film cut #goal/career #focus/Q4 #priority/medium
""",
    )


def _goal_blob(gid: str, text: str, quarter: str, priority: str, category: str) -> dict:
    return {
        "id": gid,
        "text": text,
        "quarter": quarter,
        "priority": priority,
        "category": category,
        "context": "",
        "include": "",
        "exclude": "",
        "success": "",
    }


def _seed_goals_mapping(vault: Path) -> None:
    """Format must match GoalsMapper + Main Dashboard dataview (task_id → goals[])."""
    now = datetime.now().isoformat(timespec="seconds")
    goals = {
        "g_career_demo": _goal_blob(
            "g_career_demo", "Ship public demo of the life OS", "Q3", "high", "career"
        ),
        "g_growth_papers": _goal_blob(
            "g_growth_papers", "Read one systems paper a week", "Q3", "low", "growth"
        ),
        "g_home_budget": _goal_blob(
            "g_home_budget", "Keep weekly grocery budget under 200", "Q3", "high", "home"
        ),
        "g_health_walk": _goal_blob(
            "g_health_walk", "Walk 8k steps most weekdays", "Q3", "low", "health"
        ),
        "g_exp_trip": _goal_blob(
            "g_exp_trip", "One weekend trip this quarter", "Q3", "low", "experience"
        ),
        "g_infra_budget": _goal_blob(
            "g_infra_budget", "Harden agent budget gates", "Q3", "high", "infrastructure"
        ),
    }

    def entry(task_id: str, title: str, goal_ids: list[str]) -> tuple[str, dict]:
        return task_id, {
            "task_title": title,
            "goal_ids": goal_ids,
            "goals": [goals[g] for g in goal_ids if g in goals],
        }

    pairs = [
        entry("a4000001", "Ship demo vault seed", ["g_career_demo"]),
        entry("a4000002", "Rewrite onboarding docs", ["g_growth_papers"]),
        entry("a4000003", "Polish finance dashboard charts", ["g_infra_budget"]),
        entry("a6000001", "Ship docs", ["g_career_demo"]),
        entry("a6000002", "Open issue", ["g_career_demo"]),
        entry("a6000003", "Fix CI badges", ["g_infra_budget"]),
        entry("a6000004", "Draft trip plan note", ["g_exp_trip"]),
        entry("a6000005", "Weekly grocery run", ["g_home_budget"]),
        entry("a1000001", "Plan Q4 goals workshop", ["g_career_demo"]),
        entry("a1000002", "Read systems design notes", ["g_growth_papers"]),
        entry("a2000001", "Renew domain registration", ["g_infra_budget"]),
        entry("a2000003", "Book weekend train tickets", ["g_exp_trip"]),
        entry("a2000002", "Book dentist checkup", ["g_health_walk"]),
    ]
    readable = dict(pairs)
    mapping = {
        "task_to_goals": {tid: info["goal_ids"] for tid, info in readable.items()},
        "task_titles": {tid: info["task_title"] for tid, info in readable.items()},
        "readable_mapping": readable,
        "last_updated": now,
    }
    # Scaffold dataview path: 300_Dashboards/goals_task_mapping.json
    path = vault / DASH / "goals_task_mapping.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {path}")
    # Mirror under Data/ for older scripts that look there
    mirror = vault / DASH / DATA / "goals_task_mapping.json"
    mirror.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"  wrote {mirror}")


def _log_event(ts: str, typ: str, data: dict) -> str:
    body = json.dumps(data, ensure_ascii=False, indent=2)
    return f"## {ts}\n\n**Type:** {typ}\n\n**Data:**\n```json\n{body}\n```\n\n---\n\n"


def _seed_action_logs(vault: Path) -> None:
    """~120 days of creates/moves/completions — planning + kanban-flow charts fill smoothly."""
    today = date.today()
    titles = [
        ("Ship docs", "career", "high"),
        ("Open issue", "career", "high"),
        ("Fix CI badges", "infrastructure", "high"),
        ("Draft trip plan note", "experience", "low"),
        ("Weekly grocery run", "home", "low"),
        ("Review pull request", "career", "high"),
        ("Update onboarding", "growth", "high"),
        ("Pay utilities", "home", "low"),
        ("Gym session plan", "health", "low"),
        ("Refactor chart tools", "infrastructure", "high"),
        ("Write test cases", "infrastructure", "high"),
        ("Sync with design", "career", "high"),
        ("Read chapter notes", "study", "low"),
        ("Plan sprint retro", "career", "high"),
        ("Organize inbox", "home", "low"),
        ("Update dependencies", "infrastructure", "high"),
        ("Coffee with mentor", "growth", "low"),
        ("Book flights", "experience", "low"),
        ("Stretch routine", "health", "low"),
        ("Debug flaky test", "infrastructure", "high"),
    ]
    by_month: dict[str, list[str]] = {}

    for day_i in range(DEMO_HISTORY_DAYS, -1, -1):
        d = today - timedelta(days=day_i)
        month_key = d.strftime("%Y-%m")
        wave = 1.0 + 0.35 * math.sin(day_i / 9.0) + 0.15 * math.cos(day_i / 17.0)
        n_done = max(1, min(5, int(round(2.5 * wave))))
        day_chunks: list[str] = []
        for j in range(n_done):
            title, cat, prio = titles[(day_i + j) % len(titles)]
            tid = f"demo{d.strftime('%m%d')}{j:02d}"
            hour = 8 + j * 2 + (day_i % 3)
            day_chunks.append(
                _log_event(
                    f"{d.isoformat()} {hour:02d}:15:00",
                    "task_created",
                    {"task_id": tid, "title": title, "category": cat, "priority": prio},
                )
            )
            day_chunks.append(
                _log_event(
                    f"{d.isoformat()} {hour:02d}:35:00",
                    "task_moved",
                    {
                        "task_id": tid,
                        "title": title,
                        "from": COL_BACKLOG,
                        "to": COL_IN_PROGRESS,
                        "priority": prio,
                    },
                )
            )
            day_chunks.append(
                _log_event(
                    f"{d.isoformat()} {hour + 1:02d}:50:00",
                    "task_completed",
                    {"task_id": tid, "title": title, "category": cat, "priority": prio},
                )
            )
        if day_i % 4 == 0:
            tid = f"wip{day_i}"
            day_chunks.append(
                _log_event(
                    f"{d.isoformat()} 11:00:00",
                    "task_created",
                    {
                        "task_id": tid,
                        "title": f"Carry-over item {day_i}",
                        "category": "career",
                        "priority": "high",
                    },
                )
            )
            day_chunks.append(
                _log_event(
                    f"{d.isoformat()} 11:20:00",
                    "task_moved",
                    {
                        "task_id": tid,
                        "title": f"Carry-over item {day_i}",
                        "from": COL_BACKLOG,
                        "to": COL_WAITING,
                        "priority": "high",
                    },
                )
            )
        if day_i % 7 == 0:
            day_chunks.append(
                _log_event(
                    f"{d.isoformat()} 16:00:00",
                    "task_moved",
                    {
                        "task_id": f"noise{day_i}",
                        "title": f"Deferred cleanup {day_i}",
                        "from": COL_IN_PROGRESS,
                        "to": COL_DEFERRED,
                        "priority": "low",
                    },
                )
            )
        by_month.setdefault(month_key, []).extend(day_chunks)

    y = today - timedelta(days=1)
    yesterday_done = [
        ("a6000001", "Ship docs", "career", "high"),
        ("a6000002", "Open issue", "career", "high"),
        ("a6000003", "Fix CI badges", "infrastructure", "high"),
        ("a6000004", "Draft trip plan note", "experience", "low"),
        ("a6000005", "Weekly grocery run", "home", "low"),
    ]
    today_key = today.strftime("%Y-%m")
    by_month.setdefault(today_key, [])
    for i, (tid, title, cat, prio) in enumerate(yesterday_done):
        by_month[today_key].append(
            _log_event(
                f"{y.isoformat()} {10 + i:02d}:1{i}:00",
                "task_completed",
                {"task_id": tid, "title": title, "category": cat, "priority": prio},
            )
        )
    by_month[today_key].append(
        _log_event(
            f"{today.isoformat()} 09:15:00",
            "task_created",
            {
                "task_id": "a4000001",
                "title": "Ship demo vault seed",
                "category": "career",
                "priority": "high",
            },
        )
    )
    by_month[today_key].append(
        _log_event(
            f"{today.isoformat()} 09:20:00",
            "task_moved",
            {
                "task_id": "a4000001",
                "title": "Ship demo vault seed",
                "from": COL_BACKLOG,
                "to": COL_IN_PROGRESS,
                "priority": "high",
            },
        )
    )

    for month_key, chunks in sorted(by_month.items()):
        path = vault / DASH / LOGS / f"📊 Action_Logs_{month_key}.md"
        _write(path, f"# Action log (demo) — {month_key}\n\n" + "".join(chunks))
        print(f"  wrote {path} ({len(chunks)} events)")


def _seed_planning_chart_history(vault: Path) -> None:
    """Pre-fill open-pipeline + column history so charts are smooth before the first build."""
    today = date.today()
    cat_ratios = {
        "career": 0.30,
        "growth": 0.18,
        "infrastructure": 0.14,
        "home": 0.12,
        "health": 0.08,
        "experience": 0.08,
        "study": 0.10,
    }
    col_keys = [COL_BACKLOG, COL_WAITING, COL_DEFERRED, COL_IN_PROGRESS, COL_BLOCKED]
    col_base = [0.38, 0.14, 0.10, 0.28, 0.10]

    open_snaps: list[dict] = []
    col_snaps: list[dict] = []
    for day_i in range(DEMO_HISTORY_DAYS, -1, -1):
        d = today - timedelta(days=day_i)
        ds = d.isoformat()
        t = day_i / 11.0
        base_open = int(11 + 5 * math.sin(t * 0.85) + 2 * math.cos(t * 0.35))
        base_open = max(8, min(22, base_open))
        by_cat: dict[str, int] = {}
        assigned = 0
        cats = list(cat_ratios.keys())
        for i, cat in enumerate(cats[:-1]):
            n = max(0, int(base_open * cat_ratios[cat] * (0.92 + 0.08 * math.sin(t + i))))
            by_cat[cat] = n
            assigned += n
        by_cat[cats[-1]] = max(0, base_open - assigned)
        open_snaps.append(
            {
                "date": ds,
                "updated_at": f"{ds} 23:59",
                "total": sum(by_cat.values()),
                "by_category": by_cat,
            }
        )

        col_counts: dict[str, int] = {}
        rem = base_open
        for i, col in enumerate(col_keys[:-1]):
            share = col_base[i] * (0.9 + 0.12 * math.sin(t + i * 0.7))
            n = max(0, int(base_open * share))
            col_counts[col] = n
            rem -= n
        col_counts[col_keys[-1]] = max(0, rem)
        mapped = int(base_open * (0.82 + 0.06 * math.sin(t * 0.5)))
        col_snaps.append(
            {
                "date": ds,
                "updated_at": f"{ds} 23:59",
                "total_open": base_open,
                "by_column": col_counts,
                "by_goal_segment": {
                    "goal_mapped": mapped,
                    "unmapped": max(0, base_open - mapped),
                    "daily_routine": max(0, int(base_open * 0.06)),
                },
                "source": "seed",
            }
        )

    planning_dir = vault / DASH / "Charts" / "Planning"
    planning_dir.mkdir(parents=True, exist_ok=True)
    open_path = planning_dir / "open_tasks_by_day_history.json"
    col_path = planning_dir / "kanban_columns_by_day_history.json"
    open_path.write_text(
        json.dumps({"snapshots": open_snaps}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    col_path.write_text(
        json.dumps({"version": 1, "snapshots": col_snaps}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote {open_path} ({len(open_snaps)} days)")
    print(f"  wrote {col_path} ({len(col_snaps)} days)")



def _seed_knowledge(vault: Path) -> None:
    """Legacy stubs kept for Trip_Plan etc., then dense graph pack."""
    # Minimal evergreen notes (hubs link these)
    stubs = {
        f"{KNOWLEDGE}/{NOTES}/Trip_Plan.md": """---
type: note
title: Trip plan
created: 2026-08-20
tags: [travel, demo, domain/experience]
summary: Synthetic weekend trip outline for knowledge demo
---

# Trip plan

## Short
- Friday evening train
- Saturday museum + coffee
- Sunday park walk

See [[Harbor_Park]], [[Book weekend train tickets]] vibe in tasks, [[Sheet_Pan_Salmon]] for meals.
""",
        f"{KNOWLEDGE}/{NOTES}/Agent_Budgets.md": """---
type: note
title: Agent budgets
created: 2026-08-25
tags: [agent, harness, demo, domain/infrastructure]
summary: Notes about clip_ratio and context budgets
---

# Agent budgets

Calibrate `tool_result_max_chars` from day-log dump sizes.
Watch `clip_ratio` in agent traces before raising temperature.
Related: [[Budget_Quality_Gate]], [[Agent_Eval_Notes]].
""",
        f"{KNOWLEDGE}/{NOTES}/Coffee_Shops.md": """---
type: note
title: Coffee shops
created: 2026-08-18
tags: [food, demo, domain/experience]
---

# Coffee shops

- Northside Roasters — quiet mornings
- Harbor Brew — laptop-friendly

See [[Quiet_Cafe_North]], [[Deep_Work_Blocks]].
""",
        f"{KNOWLEDGE}/Books/Designing_Data_Intensive_Apps.md": """---
type: book
title: Designing Data-Intensive Applications
created: 2026-08-10
tags: [books, systems, demo, domain/study]
status: reading
---

# Designing Data-Intensive Applications

Notes: replication vs partitioning; keep the demo vault offline-first.
Also: [[System_Design_Primer]], [[Thinking_in_Systems]].
""",
        f"{KNOWLEDGE}/Books/Atomic_Habits.md": """---
type: book
title: Atomic Habits
created: 2026-07-01
tags: [books, habits, demo, domain/growth]
status: finished
---

# Atomic Habits

Cue → craving → response → reward. Tie routines to [[Walk_8k_habit]].
""",
        f"{KNOWLEDGE}/Places/Harbor_Park.md": """---
type: place
title: Harbor Park
created: 2026-08-12
tags: [places, outdoor, demo, domain/health]
---

# Harbor Park

Good for Sunday walks. Quiet after 17:00. Pair with [[River_Trail]].
""",
        f"{KNOWLEDGE}/Places/Northside_Library.md": """---
type: place
title: Northside Library
created: 2026-08-05
tags: [places, focus, demo, domain/study]
---

# Northside Library

Deep-work spot. Free Wi‑Fi, power outlets on level 2. See [[Quiet_Cafe_North]].
""",
        f"{KNOWLEDGE}/Ideas/Life_OS_Film_Beats.md": """---
type: idea
title: Life OS film beats
created: 2026-08-26
tags: [ideas, demo, product, domain/career]
---

# Life OS film beats

Hero: tasks × spend × chart in Telegram, same PNG in Obsidian.
[[Chart_in_Telegram_Hero]], [[Graph_View_Demo]].
""",
        f"{KNOWLEDGE}/Ideas/Weekly_Review_Template.md": """---
type: idea
title: Weekly review template
created: 2026-08-15
tags: [ideas, review, demo, domain/growth]
---

# Weekly review template

1. Wins
2. Stuck
3. Next week focus (max 3)

Handwritten: [[Sunday_Reset]].
""",
        f"{KNOWLEDGE}/Recipes/Overnight_Oats.md": """---
type: recipe
title: Overnight oats
created: 2026-08-08
tags: [recipes, food, demo, domain/home]
---

# Overnight oats

Oats + milk + yogurt + berries. Prep night before. See [[Sheet_Pan_Salmon]].
""",
    }
    for rel, body in stubs.items():
        _write(vault / rel, body)

    import importlib.util
    pack_path = Path(__file__).resolve().parent / "demo" / "seed_knowledge_pack.py"
    spec = importlib.util.spec_from_file_location("seed_knowledge_pack", pack_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    mod.seed_knowledge_pack(vault)


def _seed_handwritten(vault: Path) -> None:
    """Handwritten is filled inside seed_knowledge_pack."""
    return


def _seed_routines(vault: Path) -> None:
    today = date.today()
    _write(
        vault / ROUTINES / "📅 Routines" / "📋 Tasks_Config.md",
        """
# Routines config

## 🌅 Morning routines

- [ ] Make coffee
- [ ] Review calendar (5 min)
- [ ] Open top 3 tasks

## ☀️ Daytime routines

- [ ] Stand / stretch hourly
- [ ] Drink water

## 🌙 Evening routines

- [ ] Log meals / steps
- [ ] Inbox zero (or park)
- [ ] Prep tomorrow's top 3
""",
    )
    hist_lines = ["# Routines history\n"]
    for i in range(90, 0, -1):
        d = today - timedelta(days=i)
        wave = 0.75 + 0.2 * math.sin(i / 8.0)
        ok_m = (i % 5 != 0) or (i % 11 == 0)
        ok_d = (i % 4 != 0) or (i % 13 == 0)
        ok_e = wave > 0.82 or (i % 3 != 0)
        hist_lines.append(f"## {d.isoformat()}\n")
        hist_lines.append(f"- Morning: {'✅' if ok_m else '❌'}\n")
        hist_lines.append(f"- Day: {'✅' if ok_d else '❌'}\n")
        hist_lines.append(f"- Evening: {'✅' if ok_e else '❌'}\n\n")
    _write(vault / ROUTINES / "📊 Routines_History.md", "".join(hist_lines))

    today_json = {
        "date": today.isoformat(),
        "status": {"morning": True, "day": False, "evening": False},
        "items": {
            "morning": ["Make coffee", "Review calendar (5 min)", "Open top 3 tasks"],
            "day": ["Stand / stretch hourly", "Drink water"],
            "evening": ["Log meals / steps", "Inbox zero (or park)", "Prep tomorrow's top 3"],
        },
    }
    path = vault / ROUTINES / DATA / "routines_today.json"
    path.write_text(json.dumps(today_json, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {path}")

    _write(
        vault / ROUTINES / "📊 Signals" / "📋 Signals_Config.md",
        """
# Signals config

Track mood / energy once per evening (1–5).

```yaml
signals:
  - id: mood
    label: Mood
    scale: 1-5
  - id: energy
    label: Energy
    scale: 1-5
  - id: focus
    label: Focus
    scale: 1-5
```
""",
    )
    sig_lines = ["# Signals history\n", "| Date | Mood | Energy | Focus |\n|---|---:|---:|---:|\n"]
    for i in range(90, 0, -1):
        d = today - timedelta(days=i)
        mood = 3 + int(1.2 * math.sin(i / 6.0) + 0.5 * math.cos(i / 14.0))
        energy = 3 + int(1.0 * math.sin(i / 9.0 + 1.0))
        focus = 3 + int(0.9 * math.cos(i / 7.0))
        mood = max(1, min(5, mood))
        energy = max(1, min(5, energy))
        focus = max(1, min(5, focus))
        sig_lines.append(f"| {d.isoformat()} | {mood} | {energy} | {focus} |\n")
    _write(vault / ROUTINES / "📊 Signals" / "📊 Signals_History.md", "".join(sig_lines))
    _write(
        vault / ROUTINES / "📊 Signals" / "📋 Signals_Config.yaml",
        """
signals:
  - id: mood
    label: Mood
    scale: 1-5
  - id: energy
    label: Energy
    scale: 1-5
  - id: focus
    label: Focus
    scale: 1-5
""",
    )
    # EN stats hubs (vault-templates/routines/*.template is still RU — don't use scaffold for film)
    _write(
        vault / ROUTINES / "Charts" / "Routines" / "📊 Routine_statistics.md",
        """
# 📊 Routine statistics

_Synthetic demo — morning / day / evening completion over the last two weeks._

See [[📊 Routines_History]] and [[📋 Tasks_Config]].

## Snapshot

| Window | Morning | Day | Evening |
|---|---:|---:|---:|
| Last 7 days | 86% | 71% | 71% |
| Last 14 days | 79% | 71% | 64% |

> [!tip] Film tip
> Open this note after the Task board to show habits live next to goals.
""",
    )
    _write(
        vault / ROUTINES / "Charts" / "Signals" / "📊 Signals_statistics.md",
        """
# 📊 Signals statistics

_Mood · energy · focus (1–5) from evening check-in — synthetic demo data._

See [[📊 Signals_History]].

## Last 7 days (avg)

| Signal | Avg |
|---|---:|
| Mood | 3.7 |
| Energy | 3.4 |
| Focus | 3.9 |

> [!note] Trends
> Energy dips on heavy meeting days — pair with [[📅 Meetings_and_week_focus]].
""",
    )


def _seed_calendar(vault: Path) -> None:
    today = date.today()
    lines = ["---", f"{today.strftime('%d %b %Y')} at 09:00", "---"]
    for i in range(60):
        d = today - timedelta(days=i)
        ds = d.strftime("%d.%m.%Y")
        weekday = d.weekday()
        if i == 0:
            lines.append(f"{ds} 10:00 - 10:30 [meeting] Demo standup")
            lines.append(f"{ds} 15:00 - 16:00 [meeting] Demo 1:1")
            lines.append(f"{ds} 18:00 - 19:00 [focus] Film product demo")
        elif weekday in (0, 2, 4):
            lines.append(f"{ds} 09:30 - 10:00 [meeting] Async sync")
            lines.append(f"{ds} 14:00 - 16:00 [focus] Deep work block")
        elif weekday == 1:
            lines.append(f"{ds} 11:00 - 11:45 [meeting] Sync with design")
            lines.append(f"{ds} 16:00 - 17:00 [focus] Chart polish")
        else:
            lines.append(f"{ds} 10:30 - 11:15 [meeting] Team review")
            if i % 2 == 0:
                lines.append(f"{ds} 13:00 - 14:00 [focus] Writing block")
    lines.append("")
    _write(vault / DASH / DATA / "Calendar.txt", "\n".join(lines))


def _seed_health_mac(vault: Path) -> None:
    """≥120 evening samples so health + cross-domain + analytics charts fill smoothly."""
    today = date.today()
    iphone = vault / DASH / DATA / "Actions" / "IPhone"
    for i in range(DEMO_HISTORY_DAYS):
        d = today - timedelta(days=i)
        t = i / 12.0
        steps = int(7200 + 2800 * math.sin(t * 0.9) + 900 * math.cos(t * 0.4))
        protein = int(95 + 25 * math.sin(t * 0.7))
        asleep_h = 6 + int(1.2 * math.sin(t * 0.5))
        asleep_m = 15 + int(20 * math.cos(t * 0.6)) % 45
        deep_m = 35 + int(25 * math.sin(t + 0.5))
        rem_m = 55 + int(20 * math.cos(t * 1.1))
        core_h = 3 + int(0.8 * math.sin(t * 0.8))
        core_m = 10 + int(15 * math.cos(t)) % 50
        awake_m = 8 + int(12 * math.sin(t * 1.3)) % 25
        weight = 72.4 + 0.6 * math.sin(t / 5.0)
        _write(
            iphone / f"{d.isoformat()}, 21-30.txt",
            f"""
ts: {d.isoformat()}T21:30:00
source: sample_evening
steps: {steps}
weight_kg: {weight:.1f}
resting_hr_bpm: {54 + int(4 * math.sin(t * 0.3))}
hrv_ms: {42 + int(12 * math.cos(t * 0.45))}
active_calories_kcal: {380 + int(180 * math.sin(t * 0.55))}
calories_kcal: {2050 + int(320 * math.sin(t * 0.65))}
water_ml: {1500 + int(500 * math.sin(t * 0.5))}
proteins_g: {protein}
fats_g: {62 + int(12 * math.cos(t))}
carbs_g: {195 + int(55 * math.sin(t * 0.8))}
exercise_min: {25 + int(35 * math.sin(t * 0.75))}
sleep_interval: 23:10-06:45
sleep_detail: Total Time Asleep: {asleep_h} hours {asleep_m} minutes
Deep for 1 hours and {deep_m} minutes
REM for 1 hours and {rem_m} minutes
Core for {core_h} hours and {core_m} minutes
Awake for {awake_m} minutes
note: synthetic demo sample day {i}
""",
        )
    _write(
        vault / DASH / DATA / "Actions" / "Mac" / f"{today.isoformat()}, 12-00.txt",
        f"""
ts: {today.isoformat()}T12:00:00
source: mac
app: Cursor
focus: Work
battery_pct: 80
idle_sec: 30
note: synthetic demo sample
""",
    )
    for i in range(1, 30):
        d = today - timedelta(days=i)
        if i % 2 == 0:
            _write(
                vault / DASH / DATA / "Actions" / "Mac" / f"{d.isoformat()}, 18-00.txt",
                f"""
ts: {d.isoformat()}T18:00:00
source: mac
app: Obsidian
focus: Review
battery_pct: {55 + i % 30}
idle_sec: {20 + i * 5}
note: synthetic evening sample
""",
            )


def _seed_finance_db(vault: Path) -> Path:
    db = vault / DASH / DATA / "finance.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE accounts (
          id INTEGER PRIMARY KEY,
          user_id INTEGER NOT NULL,
          name TEXT NOT NULL,
          type TEXT,
          currency TEXT,
          is_external_balance INTEGER DEFAULT 0,
          external_balance REAL DEFAULT 0,
          created_at TEXT
        );
        CREATE TABLE transactions (
          id INTEGER PRIMARY KEY,
          user_id INTEGER NOT NULL,
          account_id INTEGER NOT NULL,
          type TEXT NOT NULL,
          amount REAL NOT NULL,
          currency TEXT,
          category TEXT,
          description TEXT,
          occurred_at TEXT,
          created_at TEXT
        );
        CREATE TABLE planned_expenses (
          id INTEGER PRIMARY KEY,
          user_id INTEGER NOT NULL,
          name TEXT NOT NULL,
          amount REAL NOT NULL,
          currency TEXT,
          category TEXT,
          due_date TEXT,
          status TEXT DEFAULT 'active',
          created_at TEXT
        );
        CREATE TABLE account_balance_snapshots (
          id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
          account_id INTEGER NOT NULL,
          snapshot_date DATE NOT NULL,
          balance NUMERIC(18, 2) NOT NULL,
          UNIQUE (account_id, snapshot_date)
        );
        """
    )
    uid = 1
    card_base = 4200.0
    savings_base = 3100.0
    cur.execute(
        "INSERT INTO accounts (id, user_id, name, type, currency, is_external_balance, external_balance, created_at) "
        "VALUES (1, ?, 'Demo card', 'card', 'USD', 0, ?, datetime('now'))",
        (uid, card_base),
    )
    cur.execute(
        "INSERT INTO accounts (id, user_id, name, type, currency, is_external_balance, external_balance, created_at) "
        "VALUES (2, ?, 'Emergency savings', 'savings', 'USD', 0, ?, datetime('now'))",
        (uid, savings_base),
    )
    cur.execute(
        "INSERT INTO accounts (id, user_id, name, type, currency, is_external_balance, external_balance, created_at) "
        "VALUES (3, ?, 'Friend loan (owed to me)', 'receivable:Alex', 'USD', 1, 350, datetime('now'))",
        (uid,),
    )
    cur.execute(
        "INSERT INTO accounts (id, user_id, name, type, currency, is_external_balance, external_balance, created_at) "
        "VALUES (4, ?, 'Demo loan', 'liability_payable:Demo loan', 'USD', 1, 1200, datetime('now'))",
        (uid,),
    )
    today = date.today()
    start = today - timedelta(days=DEMO_HISTORY_DAYS)
    catalog = [
        ("Food", "Coffee", 6.5, 14.0),
        ("Food", "Lunch", 12.0, 26.0),
        ("Food", "Grocery", 28.0, 95.0),
        ("Transport", "Metro", 2.5, 8.0),
        ("Transport", "Rideshare", 11.0, 28.0),
        ("Home", "Utilities share", 18.0, 45.0),
        ("Home", "Household", 15.0, 55.0),
        ("Growth", "Books", 12.0, 38.0),
        ("Growth", "Course", 25.0, 80.0),
    ]
    txn_id = 1
    daily_card_delta: dict[date, float] = defaultdict(float)
    daily_savings_delta: dict[date, float] = defaultdict(float)

    d = start
    while d <= today:
        day_i = (today - d).days
        t = day_i / 14.0
        spend_wave = 0.85 + 0.25 * math.sin(t * 0.9) + 0.1 * math.cos(t * 0.35)
        n_tx = max(2, min(5, int(round(3.2 * spend_wave))))

        if d.day == 1:
            amt = 8500.0
            occurred = datetime(d.year, d.month, d.day, 9, 5, 0).strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                "INSERT INTO transactions (id, user_id, account_id, type, amount, currency, category, description, occurred_at, created_at) "
                "VALUES (?, ?, 1, 'income', ?, 'USD', 'Salary', 'Monthly salary (demo)', ?, datetime('now'))",
                (txn_id, uid, amt, occurred),
            )
            txn_id += 1
            daily_card_delta[d] += amt

        if d.day == 5:
            xfer = 1700.0
            occurred = datetime(d.year, d.month, d.day, 10, 0, 0).strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                "INSERT INTO transactions (id, user_id, account_id, type, amount, currency, category, description, occurred_at, created_at) "
                "VALUES (?, ?, 1, 'expense', ?, 'USD', 'Savings', 'Monthly savings (demo)', ?, datetime('now'))",
                (txn_id, uid, xfer, occurred),
            )
            txn_id += 1
            daily_card_delta[d] -= xfer
            cur.execute(
                "INSERT INTO transactions (id, user_id, account_id, type, amount, currency, category, description, occurred_at, created_at) "
                "VALUES (?, ?, 2, 'income', ?, 'USD', 'Transfer', 'From card', ?, datetime('now'))",
                (txn_id, uid, xfer, occurred),
            )
            txn_id += 1
            daily_savings_delta[d] += xfer

        if d.weekday() == 6:
            amt = 78.0 + 35.0 * (0.5 + 0.5 * math.sin(t))
            occurred = datetime(d.year, d.month, d.day, 11, 30, 0).strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                "INSERT INTO transactions (id, user_id, account_id, type, amount, currency, category, description, occurred_at, created_at) "
                "VALUES (?, ?, 1, 'expense', ?, 'USD', 'Food', 'Weekly groceries', ?, datetime('now'))",
                (txn_id, uid, round(amt, 2), occurred),
            )
            txn_id += 1
            daily_card_delta[d] -= amt

        for j in range(n_tx):
            cat, desc, lo, hi = catalog[(day_i + j) % len(catalog)]
            span = hi - lo
            amt = lo + span * (0.45 + 0.45 * math.sin(t + j * 0.8))
            hour = 8 + j * 3 + (day_i % 2)
            occurred = datetime(d.year, d.month, d.day, hour, 10 + j * 7, 0).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            cur.execute(
                "INSERT INTO transactions (id, user_id, account_id, type, amount, currency, category, description, occurred_at, created_at) "
                "VALUES (?, ?, 1, 'expense', ?, 'USD', ?, ?, ?, datetime('now'))",
                (txn_id, uid, round(amt, 2), cat, desc, occurred),
            )
            txn_id += 1
            daily_card_delta[d] -= round(amt, 2)

        d += timedelta(days=1)

    # Running balances → daily snapshots for smooth balance chart.
    card_bal = card_base
    savings_bal = savings_base
    snap_d = start
    while snap_d <= today:
        card_bal += daily_card_delta.get(snap_d, 0.0)
        savings_bal += daily_savings_delta.get(snap_d, 0.0)
        cur.execute(
            "INSERT INTO account_balance_snapshots (account_id, snapshot_date, balance) VALUES (1, ?, ?)",
            (snap_d.isoformat(), round(card_bal, 2)),
        )
        cur.execute(
            "INSERT INTO account_balance_snapshots (account_id, snapshot_date, balance) VALUES (2, ?, ?)",
            (snap_d.isoformat(), round(savings_bal, 2)),
        )
        snap_d += timedelta(days=1)

    planned = [
        ("Annual domain renewal", 45.0, "Infrastructure", (today + timedelta(days=14)).isoformat()),
        ("Weekend trip train", 120.0, "Travel", (today + timedelta(days=10)).isoformat()),
        ("Dentist checkup", 90.0, "Health", (today + timedelta(days=21)).isoformat()),
    ]
    for name, amount, cat, due in planned:
        cur.execute(
            "INSERT INTO planned_expenses (user_id, name, amount, currency, category, due_date, status, created_at) "
            "VALUES (?, ?, ?, 'USD', ?, ?, 'active', datetime('now'))",
            (uid, name, amount, cat, due),
        )
    conn.commit()
    conn.close()
    print(f"  wrote {db} ({txn_id - 1} txns, {DEMO_HISTORY_DAYS + 1} balance snapshots)")
    return db


def _seed_agent_traces(vault: Path) -> Path:
    """Synthetic agent_traces.jsonl so System / Agent cost charts fill (~90 days)."""
    path = vault / "Agent" / "logs" / "agent_traces.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    today = date.today()
    domains = ["planning", "finance", "knowledge", "planning", "finance", "health"]
    lines: list[str] = []
    for day_i in range(90):
        d = today - timedelta(days=day_i)
        wave = 1.0 + 0.4 * math.sin(day_i / 7.0)
        n_runs = max(1, min(4, int(round(2.0 * wave))))
        for j in range(n_runs):
            domain = domains[(day_i + j) % len(domains)]
            prompt = 1400 + int(3200 * (0.5 + 0.5 * math.sin(day_i / 5.0 + j)))
            completion = 220 + int(600 * (0.5 + 0.5 * math.cos(day_i / 6.0 + j)))
            cost = (prompt / 1_000_000.0) * 0.14 + (completion / 1_000_000.0) * 0.28
            ts = datetime(d.year, d.month, d.day, 9 + j * 3, 10 + j, 0).isoformat()
            row = {
                "ts": ts,
                "user_id": 1,
                "domain": domain,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
                "est_cost_usd": round(cost, 6),
                "tool_calls_executed": 1 + (j % 3),
                "tool_iters": [
                    {"tools": [{"name": n} for n in ["vault_search", "send_vault_charts"][: 1 + j % 2]]}
                ],
                "total_latency_ms": 750 + day_i * 12 + j * 90,
                "question_chars": 40 + j * 12,
                "answer_chars": 180 + j * 55,
                "end_reason": "final",
                "selected_tools": ["vault_search", "send_vault_charts"][: 1 + j % 2],
                "llm_rounds": [
                    {
                        "iter": 0,
                        "latency_ms": 750 + j * 45,
                        "model": "demo-flash",
                        "prompt_tokens": prompt,
                        "completion_tokens": completion,
                        "total_tokens": prompt + completion,
                        "tool_calls": 1 + j % 2,
                    }
                ],
            }
            lines.append(json.dumps(row, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {path} ({len(lines)} traces)")
    return path


def _seed_readme(vault: Path) -> None:
    _write(
        vault / "DEMO_VAULT_README.md",
        f"""
# Demo vault (English, synthetic) — full life OS film set

Tasks · goals · routines · knowledge · finance (USD) · health · calendar · analytics · agent cost.
Charts via `build_demo_charts.sh`. **Do not edit your daily `.env`.**

## Setup

```bash
cd Agent
cp -n .env.demo.example .env.demo
PYTHONPATH=. ./scripts/oa-python.sh scripts/seed_demo_vault.py --vault "{vault}"
./scripts/build_demo_charts.sh "{vault}"
./scripts/run_unified_bot_demo.sh
```

Open Obsidian → folder `{vault.name}` → start at `🎯 Main_Dashboard`.

## Hero beat (~35s)

> On days I closed the most tasks last week, did I also spend more on Food? Explain briefly, then send the tasks-and-spending chart from my vault.

Telegram answer + PNG → cut to same PNG under `300_Dashboards/Charts/Cross/`.

## Obsidian walk (optional B-roll)

Main → Progress → Finance → Health → Analytics → System → Task board → Routines → Knowledge hubs.

Stop demo bot → `./scripts/run_unified_bot.sh` for real life.
""",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--vault",
        type=Path,
        required=True,
        help="Absolute path to an empty/dedicated demo vault folder",
    )
    args = ap.parse_args()
    vault = args.vault.expanduser().resolve()
    _die_if_looks_like_main_vault(vault)
    vault.mkdir(parents=True, exist_ok=True)
    print(f"Seeding full EN life-OS demo vault → {vault}")
    _mkdirs(vault)
    _seed_kanban(vault)
    _seed_closed_archive(vault)
    _seed_action_logs(vault)
    _seed_planning_chart_history(vault)
    _seed_goals(vault)
    _seed_goals_mapping(vault)
    _seed_knowledge(vault)
    _seed_handwritten(vault)
    _seed_routines(vault)
    _seed_calendar(vault)
    _seed_health_mac(vault)
    _seed_finance_db(vault)
    _seed_agent_traces(vault)
    _seed_readme(vault)
    print("Done. Your main vault and Agent/.env were not modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
