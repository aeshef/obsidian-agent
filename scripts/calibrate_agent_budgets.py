#!/usr/bin/env python3
"""Calibrate agent dump/clip caps from vault action logs or fixtures.

Writes recommended floors to config/agent/budget_stats.json (gitignored) and
prints a before/after table vs current platform.yaml.

  PYTHONPATH=. ./scripts/oa-python.sh scripts/calibrate_agent_budgets.py
  PYTHONPATH=. ./scripts/oa-python.sh scripts/calibrate_agent_budgets.py --fixtures-only
  PYTHONPATH=. ./scripts/oa-python.sh scripts/calibrate_agent_budgets.py --days 14 --write
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fixture_samples() -> list[int]:
    fix = ROOT / "eval" / "fixtures" / "activity_day_dump.txt"
    if not fix.is_file():
        return []
    return [len(fix.read_text(encoding="utf-8"))]


def _vault_day_samples(days: int) -> list[dict]:
    from planning_bot.services.action_log import ActionLogger
    from planning_bot.services.action_log_tool import format_action_log
    from planning_bot.services.activity_log_query import (
        fetch_activity_events,
        format_activity_events_block,
    )
    from shared.agent.budget_caps import activity_events_default_limit
    from shared.agent.loop_context import clip_tool_result

    logger = ActionLogger()
    today = date.today()
    rows: list[dict] = []
    default_lim = activity_events_default_limit()
    for i in range(days):
        day = today - timedelta(days=i)
        full = format_action_log(logger, day=day.isoformat(), limit=0) or ""
        if not full.strip() or "нет событий" in full.lower() or "no events" in full.lower():
            # still try activity path
            pass
        entries, all_e, n_raw, tc = fetch_activity_events(
            logger,
            from_date=day,
            to_date=day,
            event_types=None,
            task_id=None,
            task_title=None,
            limit=0,
        )
        if n_raw == 0:
            continue
        block0 = format_activity_events_block(
            entries,
            all_e,
            n_raw=n_raw,
            type_counts=tc,
            filtered_type=None,
            period_start=day,
            period_end=day,
        )
        entries40, all40, n40, tc40 = fetch_activity_events(
            logger,
            from_date=day,
            to_date=day,
            event_types=None,
            task_id=None,
            task_title=None,
            limit=40,
        )
        block40 = format_activity_events_block(
            entries40,
            all40,
            n_raw=n40,
            type_counts=tc40,
            filtered_type=None,
            period_start=day,
            period_end=day,
        )
        _, st0 = clip_tool_result(block0)
        _, st40 = clip_tool_result(block40)
        unique_line = next(
            (ln for ln in block0.splitlines() if "Уникальн" in ln or "Unique" in ln.lower()),
            "",
        )
        rows.append(
            {
                "day": day.isoformat(),
                "n_raw": n_raw,
                "action_log_chars": len(full),
                "activity_full_chars": len(block0),
                "activity_limit40_chars": len(block40),
                "clip_full": st0,
                "clip_limit40": st40,
                "unique_line_prefix": unique_line[:120],
                "default_limit": default_lim,
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=21)
    p.add_argument("--fixtures-only", action="store_true")
    p.add_argument("--write", action="store_true", help="Write budget_stats.json")
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    from shared.agent.budget_caps import (
        clear_budget_caches,
        recommend_cap,
        tool_result_max_chars,
        verify_excerpt_max_chars,
    )
    from shared.agent.platform_config import load_platform_config, platform_int

    load_platform_config.cache_clear()
    clear_budget_caches()

    samples: list[int] = []
    detail: list[dict] = []
    if not args.fixtures_only:
        try:
            detail = _vault_day_samples(max(1, args.days))
            samples = [int(r["activity_full_chars"]) for r in detail]
            samples += [int(r["action_log_chars"]) for r in detail if r.get("action_log_chars")]
        except Exception as e:
            print(f"vault sample skipped: {e}", file=sys.stderr)
    samples += _fixture_samples()

    rec_tool = recommend_cap(samples)
    rec_verify = recommend_cap(
        samples,
        headroom=1.0,
        floor=platform_int("agent_budgets", "floor_chars", default=8000),
    )
    current_tool = platform_int("agent", "tool_result_max_chars", default=16000)
    # ignore stats floor for "current configured" view
    clear_budget_caches()

    report = {
        "n_days": len(detail),
        "n_samples": len(samples),
        "sample_chars": sorted(samples),
        "recommended": {
            "tool_result_chars": rec_tool,
            "verify_excerpt_chars": rec_verify,
        },
        "current_configured": {
            "tool_result_max_chars": current_tool,
            "activity_events_limit_default": platform_int(
                "planning_action_log", "activity_events_limit_default", default=200
            ),
            "activity_events_single_day_limit": platform_int(
                "planning_action_log", "activity_events_single_day_limit", default=0
            ),
        },
        "effective_note": "run with --write to apply stats floor via budget_stats.json",
        "days": detail,
    }

    print("=== agent budget calibration ===")
    print(f"samples={len(samples)} days={len(detail)}")
    if samples:
        print(f"chars min={min(samples)} p50≈{sorted(samples)[len(samples)//2]} max={max(samples)}")
    print(f"recommended tool_result_chars={rec_tool}  verify_excerpt_chars={rec_verify}")
    print(
        f"configured tool_result_max_chars={current_tool}  "
        f"activity_default={report['current_configured']['activity_events_limit_default']}  "
        f"single_day={report['current_configured']['activity_events_single_day_limit']}"
    )
    clipped_under_4k = sum(
        1 for r in detail if int(r.get("activity_full_chars") or 0) > 4000
    )
    clipped_under_16k = sum(
        1 for r in detail if int(r.get("activity_full_chars") or 0) > 16000
    )
    print(f"days where full activity dump >4k: {clipped_under_4k}/{len(detail)}")
    print(f"days where full activity dump >16k: {clipped_under_16k}/{len(detail)}")

    out_path = args.json_out
    if args.write:
        from shared.agent.budget_caps import _budget_stats_path

        out_path = out_path or _budget_stats_path()
        payload = {
            "recommended": report["recommended"],
            "n_samples": len(samples),
            "generated": True,
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        clear_budget_caches()
        print(f"wrote {out_path}")
        print(
            f"effective tool_result_max_chars={tool_result_max_chars()} "
            f"verify_excerpt={verify_excerpt_max_chars()}"
        )
    elif out_path:
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote report {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
