"""Guard: scheduled user-facing pushes must go through format_push / format_push_sections."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (module path relative to monorepo, function names that send scheduled Telegram text)
_SCHEDULED_SENDERS: list[tuple[str, tuple[str, ...]]] = [
    (
        "finance_bot/bot/scheduler.py",
        (
            "send_subscriptions_digest",
            "send_daily_txn_reminder",
            "send_daily_insight",
            "send_weekly_analysis",
            "send_badge_evening_alert",
            "send_badge_monthly_digest",
            "send_monthly_analysis",
        ),
    ),
    (
        "planning_bot/app/handlers/menus.py",
        (
            "send_morning_brief",
            "send_morning_routine_reminder",
            "send_evening_routine_reminder",
            "send_weekly_goals_no_tasks",
            "send_goals_alerts",
            "send_deadlines_alerts",
            "send_stuck_alerts",
        ),
    ),
    (
        "planning_bot/app/handlers/daily_checkin.py",
        ("send_daily_checkin_prompt",),
    ),
    (
        "planning_bot/app/handlers/reflection.py",
        ("schedule_weekly_review",),
    ),
    (
        "knowledge_bot/services/serendipity.py",
        ("_send_serendipity_text",),
    ),
    (
        "shared/memory/synth_job.py",
        ("notify_pushable",),
    ),
]


def _function_calls_format_push(path: Path, fn_name: str) -> bool:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != fn_name:
            continue
        segment = ast.get_source_segment(src, node) or ""
        return ("format_push(" in segment) or ("format_push_sections(" in segment)
    raise AssertionError(f"function {fn_name!r} not found in {path}")


def test_all_scheduled_push_senders_use_format_push():
    missing: list[str] = []
    for rel, names in _SCHEDULED_SENDERS:
        path = ROOT / rel
        assert path.is_file(), f"missing {rel}"
        for name in names:
            if not _function_calls_format_push(path, name):
                missing.append(f"{rel}::{name}")
    assert not missing, "scheduled pushes without format_push:\n" + "\n".join(missing)
