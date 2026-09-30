#!/usr/bin/env python3
"""Analytics insights: master daily panel, sleep hypotheses, charts."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

from planning_bot.core.pdmsg import pdmsg
from planning_bot.services.daily_panel import (
    build_master_panel,
    panel_to_arrays,
    write_panel_csv,
)
from shared.analytics.hypotheses import run_partial_weight_hypotheses, run_sleep_hypotheses
from shared.analytics.panel_coverage import panel_coverage
from shared.analytics.sleep_debt import compute_sleep_debt_series
from shared.analytics.life_os_scores import compute_life_os_daily
from shared.analytics.vault_analytics_config import vault_analytics_config
from shared.chart_paths import chart_path, chart_wikilink_png, charts_root, data_path, ensure_parent
from shared.vault_paths_config import folder, vault_rel_path


def _discover_vault(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / folder("tasks")).is_dir() and (p / folder("dashboards")).is_dir():
            return p
    return start.parents[3]


_FEAT_LABEL_KEYS = {
    "sleep_hours": "analytics_feat_sleep_hours",
    "sleep_awake_min": "analytics_feat_sleep_awake_min",
    "sleep_deep_min": "analytics_feat_sleep_deep_min",
    "sleep_core_min": "analytics_feat_sleep_core_min",
    "sleep_rem_min": "analytics_feat_sleep_rem_min",
    "sleep_deep_ratio": "analytics_feat_sleep_deep_ratio",
    "sleep_core_ratio": "analytics_feat_sleep_core_ratio",
    "sleep_rem_ratio": "analytics_feat_sleep_rem_ratio",
    "hrv_ms": "analytics_feat_hrv_ms",
    "resting_hr_bpm": "analytics_feat_resting_hr",
}


def _feat_label(feat: str) -> str:
    key = _FEAT_LABEL_KEYS.get(str(feat))
    if key:
        labeled = pdmsg(key, default="")
        if labeled:
            return labeled
    return str(feat).replace("_", " ")


def _direction(rho: float) -> str:
    return "↑" if float(rho) > 0 else "↓"


def _coverage_bar(cnt: int, total: int) -> str:
    if total <= 0:
        return "—"
    pct = 100.0 * cnt / total
    if pct >= 85:
        return f"**{cnt}**/{total}"
    if pct >= 55:
        tag = pdmsg("analytics_cov_tag_thin", default="thin")
        return f"**{cnt}**/{total} · {tag}"
    tag = pdmsg("analytics_cov_tag_gaps", default="gaps")
    return f"**{cnt}**/{total} · {tag}"


def _format_insight_line(row: dict) -> str:
    """Collapsed raw table row (power users)."""
    direction = _direction(row["spearman_rho"])
    fdr = row.get("p_fdr")
    p_part = f"FDR={fdr:.3f}" if fdr is not None else f"p={row['p_value']:.3f}"
    return (
        f"| {_feat_label(row['sleep_feature'])} | {row['outcome_label']} | {direction} | "
        f"{row['spearman_rho']:.2f} | {p_part} | {row['n']} |"
    )


def _signal_bullet(row: dict, *, rho_key: str = "spearman_rho") -> str:
    rho = float(row[rho_key])
    outcome = row.get("outcome_label") or pdmsg(
        "analytics_outcome_weight_delta_next", default="Δweight tomorrow"
    )
    return (
        f"- **{_feat_label(row['sleep_feature'])}** → {outcome} "
        f"{_direction(rho)} · ρ `{rho:.2f}` · n={row['n']}"
    )


def render_insights_summary_md(
    *,
    ts: str,
    window_days: int,
    panel_days: int,
    coverage: list[tuple[str, int, int]],
    hypotheses: list[dict],
    partial: list[dict],
    fdr_alpha: float = 0.05,
    top_n: int = 8,
) -> str:
    """Callout-first insights summary — no scary dense FDR tables in the open."""
    n_fdr = sum(1 for h in hypotheses if h.get("significant_fdr"))
    n_raw = sum(1 for h in hypotheses if h.get("significant_05"))
    sleep_label = pdmsg("analytics_cov_sleep", default="Sleep").lower()
    sleep_cov = next(
        (c for c in coverage if sleep_label in c[0].lower() or "sleep" in c[0].lower()),
        None,
    )
    sleep_frac = (sleep_cov[1] / sleep_cov[2]) if sleep_cov and sleep_cov[2] else 1.0

    lines: list[str] = [
        "> [!info] " + pdmsg("analytics_insights_updated_title", default="Updated"),
        f"> _{ts}_ · " + pdmsg(
            "analytics_insights_window_line",
            window_days=window_days,
            days=panel_days,
            default=f"window **{window_days}**d · panel **{panel_days}**",
        ),
        "",
    ]

    if n_fdr:
        lines.extend(
            [
                "> [!success] " + pdmsg("analytics_insights_verdict_title", default="Verdict"),
                "> ### "
                + pdmsg(
                    "analytics_insights_verdict_ok",
                    n=n_fdr,
                    alpha=fdr_alpha,
                    default=f"**{n_fdr}** FDR<{fdr_alpha}",
                ),
                "",
            ]
        )
    else:
        body = pdmsg(
            "analytics_insights_verdict_none",
            raw=n_raw,
            alpha=fdr_alpha,
            default=f"No FDR<{fdr_alpha}. Raw p<0.05: **{n_raw}**.",
        )
        if sleep_frac < 0.6:
            body += "\n> " + pdmsg(
                "analytics_insights_verdict_sleep_gap",
                days=sleep_cov[1] if sleep_cov else 0,
                total=sleep_cov[2] if sleep_cov else panel_days,
                default="Sleep coverage is thin — treat directions as hints only.",
            )
        kind = "warning" if sleep_frac < 0.6 else "abstract"
        lines.extend(
            [
                f"> [!{kind}] " + pdmsg("analytics_insights_verdict_title", default="Verdict"),
                "> ### " + pdmsg("analytics_insights_verdict_none_head", default="Nothing confirmed"),
                f"> {body}",
                "",
            ]
        )

    if coverage:
        lines.append("> [!abstract] " + pdmsg("analytics_heading_coverage", default="Coverage"))
        bits = [f"{label} {_coverage_bar(cnt, total)}" for label, cnt, total in coverage]
        lines.append("> " + " · ".join(bits))
        lines.append("")

    top = hypotheses[: min(top_n, len(hypotheses))]
    sig = [h for h in hypotheses if h.get("significant_fdr")][:top_n]
    show = sig or top
    if show:
        head = (
            pdmsg("analytics_heading_top_hypotheses", default="Top hypotheses")
            if sig
            else pdmsg("analytics_heading_weak_signals", default="Weak signals (top |ρ|)")
        )
        note = (
            ""
            if sig
            else "\n> " + pdmsg(
                "analytics_insights_weak_note",
                default="Not FDR-significant — direction only, not a fact.",
            )
        )
        lines.extend([f"> [!note] {head}{note}", ""])
        for h in show:
            lines.append(_signal_bullet(h))
        lines.append("")

    if partial:
        lines.extend(
            [
                "> [!note]- " + pdmsg("analytics_heading_partial_weight", default="Partial weight"),
                "> "
                + pdmsg(
                    "analytics_insights_partial_note",
                    default="Control: yesterday weight. Same caveat — not FDR-confirmed.",
                ),
            ]
        )
        for r in partial[:6]:
            rho = float(r["partial_rho"])
            lines.append(
                f"> - **{_feat_label(r['sleep_feature'])}** {_direction(rho)} "
                f"· ρ `{rho:.2f}` · n={r['n']}"
            )
        lines.append("")

    if top:
        from shared.obsidian_fold import fold_section

        header = pdmsg(
            "analytics_table_sleep_header",
            default="| Sleep (D−1) | Outcome | | ρ | p | n |",
        )
        table_lines = [
            header,
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for h in hypotheses[:20]:
            table_lines.append(_format_insight_line(h))
        lines.extend(
            fold_section(
                pdmsg("analytics_heading_hypothesis_table", default="Raw table"),
                table_lines,
                collapsed=True,
            )
        )

    lines.append("_" + pdmsg("analytics_summary_charts_hint", default="Charts below.") + "_")
    return "\n".join(lines) + "\n"


def main() -> int:
    os.environ.pop("PYTHONPATH", None)
    from shared.domain_messages import clear_domain_messages_cache
    from shared.locale import agent_locale

    clear_domain_messages_cache()
    agent_locale()
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=str)
    args = ap.parse_args()
    vault = Path(args.vault).resolve() if args.vault else _discover_vault(Path(__file__).resolve())
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    cfg = vault_analytics_config()
    panel_cfg = cfg.get("panel") or {}
    hyp_cfg = cfg.get("hypothesis") or {}
    min_pairs = int(panel_cfg.get("min_pairs") or 8)
    fdr_alpha = float(hyp_cfg.get("fdr_alpha") or 0.05)
    outcomes = cfg.get("outcomes") or {}
    window_days = int(panel_cfg.get("window_days") or 120)

    rows, columns = build_master_panel(vault)
    if len(rows) < min_pairs:
        print("SKIP: not enough panel days")
        return 0

    panel_csv = data_path(vault, "master_daily_panel_csv")
    write_panel_csv(panel_csv, rows, columns)

    arrays = panel_to_arrays(rows, columns)

    def _label(key: str) -> str:
        return pdmsg(key, default=key)

    extra = [str(x) for x in ((cfg.get("sleep") or {}).get("extra_predictors") or [])]
    hypotheses = run_sleep_hypotheses(
        arrays,
        outcomes=outcomes,
        label_fn=_label,
        min_pairs=min_pairs,
        extra_predictors=extra,
        fdr_alpha=fdr_alpha,
    )

    predictors = sorted(
        {c for c in arrays if c.endswith("_lag1") and ("sleep" in c.lower() or c in extra)}
    )
    partial = run_partial_weight_hypotheses(
        arrays,
        predictors=predictors,
        outcome=str(hyp_cfg.get("partial_weight_outcome") or "iphone_weight_delta_next"),
        control=str(hyp_cfg.get("partial_weight_control") or "iphone_weight_kg_lag1"),
        min_pairs=min_pairs,
        fdr_alpha=fdr_alpha,
    )

    cov_specs = [(str(s["key"]), _label(str(s["label_key"]))) for s in (cfg.get("coverage_metrics") or [])]
    coverage = panel_coverage(rows, cov_specs) if cov_specs else []

    insights_path = data_path(vault, "analytics_insights_json")
    ensure_parent(insights_path)
    doc = {
        "updated": ts,
        "panel_days": len(rows),
        "window_days": window_days,
        "coverage": [{"metric": m, "days": d, "total": t} for m, d, t in coverage],
        "hypotheses": hypotheses,
        "partial_weight": partial,
    }
    insights_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    charts_root(vault).mkdir(parents=True, exist_ok=True)
    generated: list[str] = []

    debt_cfg = cfg.get("sleep_debt") or {}
    debt_series = compute_sleep_debt_series(
        rows,
        target_hours=float(debt_cfg.get("target_hours") or 8.0),
        decay=float(debt_cfg.get("decay") or 0.9),
    )
    # Enrich rows for Life OS
    debt_by_day = {str(r["date"])[:10]: r.get("debt") for r in debt_series if not r.get("missing")}
    for r in rows:
        r["sleep_debt"] = debt_by_day.get(str(r.get("date") or "")[:10])

    # Optional: goal_mapped completions from kanban flow metrics
    try:
        flow_path = chart_path(vault, "kanban_flow_metrics_json")
        if flow_path.is_file():
            flow = json.loads(flow_path.read_text(encoding="utf-8"))
            seg = {str(x.get("date"))[:10]: x for x in (flow.get("completions_by_goal_segment") or [])}
            debt_flow = {str(x.get("date"))[:10]: x for x in (flow.get("daily_flow") or [])}
            prev_debt = None
            for r in rows:
                d = str(r.get("date") or "")[:10]
                r["goal_mapped_completions"] = (seg.get(d) or {}).get("goal_mapped")
                fd = (debt_flow.get(d) or {}).get("flow_debt")
                if fd is not None and prev_debt is not None:
                    r["flow_debt_delta"] = float(fd) - float(prev_debt)
                if fd is not None:
                    prev_debt = float(fd)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass

    # Calendar attention hours → Life OS Drain (not raw invite load)
    try:
        from datetime import date as _date
        from datetime import timedelta as _td

        from planning_bot.core.config import CALENDAR_JSON_FILE
        from planning_bot.services.calendar_analytics import daily_meeting_hours_series

        if CALENDAR_JSON_FILE.is_file():
            cal = json.loads(CALENDAR_JSON_FILE.read_text(encoding="utf-8"))
            events = cal.get("events") or []
            end_d = _date.today()
            start_d = end_d - _td(days=max(window_days, 120))
            meet_by_day = daily_meeting_hours_series(events, start=start_d, end=end_d)
            for r in rows:
                d = str(r.get("date") or "")[:10]
                m = meet_by_day.get(d)
                if not m:
                    continue
                r["meeting_invite_hours"] = m.get("invite_hours")
                r["meeting_hours"] = m.get("attention_hours")  # Drain uses attention
    except (OSError, json.JSONDecodeError, TypeError, ValueError, ImportError):
        pass

    life_cfg = cfg.get("life_os") or {}
    life_series = compute_life_os_daily(
        rows,
        mid=float(life_cfg.get("mid") or 50),
        high_drain=float(life_cfg.get("high_drain") or 65),
    )
    life_path = data_path(vault, "life_os_daily_json")
    ensure_parent(life_path)
    life_path.write_text(
        json.dumps({"updated": ts, "rows": life_series}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Persist enriched observations, not a second set of static images.
    write_panel_csv(panel_csv, rows, sorted(set(columns) | {k for r in rows for k in r}))

    summary_md = chart_path(vault, "chart_analytics_insights_md")
    summary_md.write_text(
        render_insights_summary_md(
            ts=ts,
            window_days=window_days,
            panel_days=len(rows),
            coverage=coverage,
            hypotheses=hypotheses,
            partial=partial,
            fdr_alpha=fdr_alpha,
            top_n=int(hyp_cfg.get("top_significant") or 8),
        ),
        encoding="utf-8",
    )

    print(f"OK: {insights_path}, {panel_csv}, charts={','.join(generated) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
