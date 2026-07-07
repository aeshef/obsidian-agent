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
    chart_panel_correlations,
    chart_sleep_hours,
    chart_sleep_stages,
    chart_sleep_weight_scatter,
    chart_weight_trend,
    panel_coverage,
)
from shared.analytics.vault_analytics_config import vault_analytics_config
from shared.chart_paths import chart_path, chart_wikilink_png, charts_root, data_path, ensure_parent
from shared.vault_paths_config import folder, vault_rel_path


def _discover_vault(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / folder("tasks")).is_dir() and (p / folder("dashboards")).is_dir():
            return p
    return start.parents[3]


def _format_insight_line(row: dict) -> str:
    direction = "↑" if row["spearman_rho"] > 0 else "↓"
    fdr = row.get("p_fdr")
    p_part = f"FDR p={fdr:.4f}" if fdr is not None else f"p={row['p_value']:.4f}"
    return (
        f"| {row['sleep_feature']} | {row['outcome_label']} | {direction} | "
        f"{row['spearman_rho']:.3f} | {p_part} | {row['n']} |"
    )


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
    top_table = hypotheses[: min(20, len(hypotheses))]

    lines = [
        pdmsg("chart_updated_window_panel", ts=ts, window_days=window_days, days=len(rows)),
        "",
    ]

    if coverage:
        lines.append(f"## {pdmsg('analytics_heading_coverage')}")
        lines.append(pdmsg("analytics_table_coverage_header"))
        lines.append("| --- | --- |")
        for label, cnt, total in coverage:
            lines.append(f"| {label} | {cnt} / {total} |")
        lines.append("")

    if top_table:
        lines.append(f"## {pdmsg('analytics_heading_hypothesis_table')}")
        lines.append(pdmsg("analytics_table_sleep_header"))
        lines.append("| --- | --- | --- | --- | --- | --- |")
        lines.extend(_format_insight_line(h) for h in top_table)
        lines.append("")

    if partial:
        lines.append(f"## {pdmsg('analytics_heading_partial_weight')}")
        for r in partial[:8]:
            direction = "↑" if r["partial_rho"] > 0 else "↓"
            lines.append(
                f"- **{r['sleep_feature']}** {direction} Δweight tomorrow "
                f"(partial ρ={r['partial_rho']:.3f}, FDR p={r.get('p_fdr', r['p_value']):.4f}, n={r['n']})"
            )
        lines.append("")

    lines.append(f"_{pdmsg('analytics_summary_charts_hint')}_")
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"OK: {insights_path}, {panel_csv}, charts={','.join(generated) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
