"""Run offline golden harness cases."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = Path(__file__).resolve().parent / "cases"


def _load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    files = sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml")) + sorted(path.glob("*.json"))
    for f in files:
        text = f.read_text(encoding="utf-8")
        if f.suffix == ".json":
            data = json.loads(text)
            if isinstance(data, list):
                cases.extend(data)
            elif isinstance(data, dict):
                cases.append(data)
            continue
        for doc in yaml.safe_load_all(text):
            if isinstance(doc, dict) and doc.get("kind"):
                cases.append(doc)
    return cases


def _run_case(case: dict[str, Any]) -> None:
    kind = case["kind"]
    inp = case.get("input") or {}
    expect = case.get("expect") or {}

    if kind == "category_match":
        from shared.finance.category_match import category_matches

        got = bool(category_matches(inp.get("parent"), inp.get("leaf")))
        want = bool(expect.get("matches"))
        if got != want:
            raise AssertionError(f"category_matches={got}, expected {want}")
        return

    if kind == "cheap_router":
        from shared.agent.cheap_router import cheap_route_domain, clear_cheap_router_cache
        from shared.telegram.host.agent import _looks_finance_planning_cross

        clear_cheap_router_cache()
        got = cheap_route_domain(
            str(inp.get("text") or ""),
            enabled=list(inp.get("enabled") or []),
            cross_domain_check=_looks_finance_planning_cross,
        )
        want = expect.get("domain")
        if got != want:
            raise AssertionError(f"cheap_router={got!r}, expected {want!r}")
        return

    if kind == "cross_domain":
        from shared.telegram.host.agent import _looks_finance_planning_cross

        got = bool(_looks_finance_planning_cross(str(inp.get("text") or "")))
        want = bool(expect.get("looks_cross"))
        if got != want:
            raise AssertionError(f"looks_cross={got}, expected {want}")
        return

    if kind == "period_compare_format":
        from shared.finance.txn_query import format_period_compare

        text = format_period_compare(
            label_a=str(inp.get("label_a") or ""),
            total_a=float(inp.get("total_a") or 0),
            label_b=str(inp.get("label_b") or ""),
            total_b=float(inp.get("total_b") or 0),
            category=inp.get("category"),
        )
        for frag in expect.get("contains") or []:
            if str(frag) not in text:
                raise AssertionError(f"missing {frag!r} in:\n{text}")
        return

    if kind == "charts_catalog":
        from shared.charts_catalog import iter_config_chart_keys

        keys = iter_config_chart_keys()
        min_keys = int(expect.get("min_keys") or 1)
        if len(keys) < min_keys:
            raise AssertionError(f"chart keys={len(keys)} < {min_keys}")
        return

    if kind == "working_set_observe":
        from shared.memory import working_set as ws

        ws.clear_working_set()
        ws.clear_working_set_pattern_cache()
        ws.observe_tool_output(
            1,
            "unified",
            str(inp.get("tool_name") or "tool"),
            str(inp.get("content") or ""),
        )
        got = ws.get_working_set(1, "unified")
        for ent in expect.get("entities_contains") or []:
            if str(ent) not in got.entities:
                raise AssertionError(f"missing entity {ent!r} in {list(got.entities)}")
        return

    if kind == "conversation_contract":
        from shared.agent.config import agent_config_dir
        from shared.prompts import load_prompt

        stem = str(inp.get("prompt_stem") or "host_query")
        # Prefer example when personal prompt is missing / stripped.
        text = load_prompt(agent_config_dir(), stem, subdir="prompts", required=False) or ""
        if not text.strip():
            example = agent_config_dir() / "prompts" / f"{stem}.example.txt"
            text = example.read_text(encoding="utf-8") if example.is_file() else ""
        any_markers = expect.get("contains_any") or expect.get("contains") or []
        if not any(str(m) in text for m in any_markers):
            raise AssertionError(
                f"prompt {stem!r} missing any of {any_markers}; len={len(text)}"
            )
        return

    raise AssertionError(f"unknown kind: {kind}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline agent golden harness")
    parser.add_argument(
        "--cases",
        type=Path,
        default=CASES_DIR,
        help="Directory with YAML/JSON golden cases",
    )
    args = parser.parse_args(argv)

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    cases = _load_cases(args.cases)
    if not cases:
        print(f"No cases in {args.cases}", file=sys.stderr)
        return 2

    failed = 0
    for case in cases:
        cid = case.get("id") or case.get("kind") or "?"
        try:
            _run_case(case)
            print(f"PASS  {cid}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {cid}: {e}", file=sys.stderr)

    print(f"{len(cases) - failed}/{len(cases)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
