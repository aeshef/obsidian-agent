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
from shared.analytics.daily_panel import (
    build_master_panel,
    panel_to_arrays,
    write_panel_csv,
)
from shared.analytics.hypotheses import run_partial_weight_hypotheses, run_sleep_hypotheses
from shared.analytics.panel_charts import (
    chart_dual_zscore,
    chart_life_os_regimes,
    chart_life_os_scores,
    chart_panel_correlations,
    chart_sleep_debt,
    chart_sleep_hours,
    chart_sleep_stages,
    chart_sleep_weight_scatter,
    chart_weight_trend,
    panel_coverage,
)
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


def _write_chart_note(vault: Path, md_key: str, png_key: str, title: str, ts: str, *, extra: str = "") -> None:
    body = f"# {title}\n\n{pdmsg('chart_updated_at', ts=ts)}"
    if extra:
        body += f"\n\n{extra}"
    body += f"\n\n{chart_wikilink_png(png_key)}\n"
    chart_path(vault, md_key).write_text(body, encoding="utf-8")


def _heatmap(
    hypotheses: list[dict],
    *,
    sleep_top: int,
    outcome_top: int,
    title: str,
    png_path: Path,
) -> bool:
    if not hypotheses:
        return False
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    by_sleep: dict[str, float] = {}
    by_out: dict[str, float] = {}
    for h in hypotheses:
        sf = str(h["sleep_feature"])
        oc = str(h["outcome"])
        by_sleep[sf] = max(by_sleep.get(sf, 0.0), float(h["abs_rho"]))
        by_out[oc] = max(by_out.get(oc, 0.0), float(h["abs_rho"]))
    top_sleep = [k for k, _ in sorted(by_sleep.items(), key=lambda x: -x[1])[:sleep_top]]
    top_out = [k for k, _ in sorted(by_out.items(), key=lambda x: -x[1])[:outcome_top]]
    if not top_sleep or not top_out:
        return False

    mat = np.full((len(top_sleep), len(top_out)), np.nan)
    lookup = {(h["sleep_feature"], h["outcome"]): h["spearman_rho"] for h in hypotheses}
    for i, sf in enumerate(top_sleep):
        for j, oc in enumerate(top_out):
            v = lookup.get((sf, oc))
            if v is not None:
                mat[i, j] = float(v)

    labels_out = []
    for oc in top_out:
        match = next((h for h in hypotheses if h["outcome"] == oc), None)
        labels_out.append(str(match["outcome_label"]) if match else oc)

    fig, ax = plt.subplots(figsize=(max(8, len(top_out) * 0.9), max(4, len(top_sleep) * 0.55)))
    im = ax.imshow(mat, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(top_out)))
    ax.set_yticks(range(len(top_sleep)))
    ax.set_xticklabels(labels_out, rotation=30, ha="right", fontsize=8)
    ax.set_yticklabels(top_sleep, fontsize=8)
    for i in range(len(top_sleep)):
        for j in range(len(top_out)):
            v = mat[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7, color="#222")
    fig.colorbar(im, ax=ax, fraction=0.046)
    ax.set_title(title, fontsize=11)
    fig.tight_layout()
    ensure_parent(png_path)
    fig.savefig(png_path, dpi=144, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


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

    chart_specs = [
        ("chart_analytics_weight_trend_png", "chart_analytics_weight_trend_md", "analytics_title_weight_trend",
         lambda p: chart_weight_trend(rows, p, title=pdmsg("analytics_title_weight_trend"))),
        ("chart_analytics_sleep_trend_png", "chart_analytics_sleep_trend_md", "analytics_title_sleep_trend",
         lambda p: chart_sleep_hours(rows, p, title=pdmsg("analytics_title_sleep_trend"))),
        ("chart_analytics_sleep_stages_png", "chart_analytics_sleep_stages_md", "analytics_title_sleep_stages",
         lambda p: chart_sleep_stages(rows, p, title=pdmsg("analytics_title_sleep_stages"))),
        ("chart_analytics_sleep_weight_png", "chart_analytics_sleep_weight_md", "analytics_title_sleep_weight",
         lambda p: chart_sleep_weight_scatter(rows, p, title=pdmsg("analytics_title_sleep_weight"), min_pairs=min_pairs)),
        ("chart_analytics_tasks_sleep_png", "chart_analytics_tasks_sleep_md", "analytics_title_tasks_sleep",
         lambda p: chart_dual_zscore(
             rows, "tasks_completed", "iphone_sleep_hours_lag1", p,
             x_label=pdmsg("cross_label_tasks"), y_label=pdmsg("analytics_label_sleep_hours_lag1"),
             title=pdmsg("analytics_title_tasks_sleep"), min_pairs=min_pairs,
         )),
    ]
    corr_keys_cfg = cfg.get("panel_correlation_keys") or []
    if corr_keys_cfg:
        keys = [str(x["key"]) for x in corr_keys_cfg]
        labels = [_label(str(x["label_key"])) for x in corr_keys_cfg]
        png = chart_path(vault, "chart_analytics_panel_corr_png")
        if chart_panel_correlations(
            rows, png, keys=keys, labels=labels,
            title=pdmsg("analytics_title_panel_corr"), min_pairs=min_pairs,
        ):
            generated.append("panel_corr")
            _write_chart_note(vault, "chart_analytics_panel_corr_md", "chart_analytics_panel_corr_png",
                              pdmsg("analytics_title_panel_corr"), ts)

    for png_key, md_key, title_key, fn in chart_specs:
        png = chart_path(vault, png_key)
        if fn(png):
            generated.append(png_key)
            _write_chart_note(vault, md_key, png_key, pdmsg(title_key), ts)

    debt_cfg = cfg.get("sleep_debt") or {}
    debt_series = compute_sleep_debt_series(
        rows,
        target_hours=float(debt_cfg.get("target_hours") or 8.0),
        decay=float(debt_cfg.get("decay") or 0.9),
    )
    # Enrich rows for Life OS
    debt_by_day = {str(r["date"])[:10]: r.get("debt") for r in debt_series}
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

    debt_png = chart_path(vault, "chart_analytics_sleep_debt_png")
    if chart_sleep_debt(
        debt_series,
        debt_png,
        title=pdmsg("analytics_title_sleep_debt"),
        label_debt=pdmsg("analytics_label_sleep_debt"),
        label_sleep=pdmsg("analytics_label_sleep_hours_axis"),
        label_target=pdmsg("analytics_label_sleep_target"),
        label_gap=pdmsg("analytics_label_sleep_gap") or "no data (debt frozen)",
    ):
        generated.append("sleep_debt")
        _write_chart_note(
            vault,
            "chart_analytics_sleep_debt_md",
            "chart_analytics_sleep_debt_png",
            pdmsg("analytics_title_sleep_debt"),
            ts,
            extra=pdmsg("analytics_sleep_debt_how").strip(),
        )

    scores_png = chart_path(vault, "chart_analytics_life_os_scores_png")
    if chart_life_os_scores(
        life_series,
        scores_png,
        title=pdmsg("analytics_title_life_os_scores"),
        label_capacity=pdmsg("analytics_label_capacity"),
        label_output=pdmsg("analytics_label_output"),
        label_drain=pdmsg("analytics_label_drain"),
        label_axis=pdmsg("analytics_label_percentile_axis"),
    ):
        from planning_bot.services.calendar_analytics import work_attention_weight

        generated.append("life_os_scores")
        _write_chart_note(
            vault,
            "chart_analytics_life_os_scores_md",
            "chart_analytics_life_os_scores_png",
            pdmsg("analytics_title_life_os_scores"),
            ts,
            extra=(
                pdmsg("analytics_life_os_scores_how").strip()
                + "\n\n"
                + pdmsg(
                    "analytics_life_os_calendar_attention_note",
                    work_weight=work_attention_weight(),
                )
            ),
        )

    regimes_png = chart_path(vault, "chart_analytics_life_os_regimes_png")
    if chart_life_os_regimes(
        life_series,
        regimes_png,
        title=pdmsg("analytics_title_life_os_regimes"),
        regime_labels={
            "flow": pdmsg("analytics_regime_flow"),
            "charge": pdmsg("analytics_regime_charge"),
            "overreach": pdmsg("analytics_regime_overreach"),
            "recovery": pdmsg("analytics_regime_recovery"),
        },
    ):
        generated.append("life_os_regimes")
        _write_chart_note(
            vault,
            "chart_analytics_life_os_regimes_md",
            "chart_analytics_life_os_regimes_png",
            pdmsg("analytics_title_life_os_regimes"),
            ts,
            extra=pdmsg("analytics_life_os_regimes_how").strip(),
        )

    heat_png = chart_path(vault, "chart_analytics_sleep_heatmap_png")
    drew_heat = _heatmap(
        hypotheses,
        sleep_top=int(hyp_cfg.get("heatmap_sleep_top") or 8),
        outcome_top=int(hyp_cfg.get("heatmap_outcome_top") or 10),
        title=pdmsg("analytics_title_sleep_heatmap"),
        png_path=heat_png,
    )
    if drew_heat:
        generated.append("heatmap")
        _write_chart_note(vault, "chart_analytics_sleep_heatmap_md", "chart_analytics_sleep_heatmap_png",
                          pdmsg("analytics_title_sleep_heatmap"), ts)

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
