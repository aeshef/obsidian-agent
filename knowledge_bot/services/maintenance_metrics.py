"""Vault maintenance snapshots, history YAML, and chart generation."""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from knowledge_bot.core.config import load_config
from knowledge_bot.services.reprocess_candidates import (
    discover_candidate_paths,
    load_reprocess_yaml,
)


def history_path(vault: Path) -> Path:
    from shared.vault_paths_config import dashboards_sub, folder

    return vault / folder("dashboards") / dashboards_sub("data") / "vault_maintenance_history.yaml"


def charts_dir(vault: Path) -> Path:
    from shared.vault_paths_config import dashboards_sub, folder

    return vault / folder("dashboards") / dashboards_sub("charts")


def _count_md(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for p in root.rglob("*.md") if p.is_file())


def _count_md_excluding_subdir(root: Path, exclude_part: str) -> int:
    if not root.is_dir():
        return 0
    n = 0
    for p in root.rglob("*.md"):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if exclude_part in rel.parts:
            continue
        n += 1
    return n


def _dir_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def collect_vault_snapshot(vault: Path) -> dict[str, Any]:
    """Quick snapshot before/after maintenance (read-only)."""
    from shared.vault_layout import knowledge_subdir

    cfg = load_config()
    agent = cfg.agent_config_path
    rpcfg = load_reprocess_yaml(agent)
    db = vault / knowledge_subdir()
    exp = db / "Export"
    notes_all = _count_md(db)
    notes_no_exp = _count_md_excluding_subdir(db, "Export")
    return {
        "notes_md_db700": notes_all,
        "notes_md_excl_export": notes_no_exp,
        "bytes_db700": _dir_size(db),
        "bytes_export": _dir_size(exp),
        "reprocess_total": len(discover_candidate_paths(vault, rpcfg, skip_if_flag=False)),
        "reprocess_eligible": len(discover_candidate_paths(vault, rpcfg, skip_if_flag=True)),
    }


def extract_step_metrics(step_name: str, stdout: str, stderr: str = "") -> dict[str, Any]:
    """Parse numeric totals from maintenance step stdout/stderr."""
    from knowledge_bot.i18n.domain_text import maintenance as mm

    text = stdout or ""
    if not text.strip() and not (stderr or "").strip():
        return {}
    out: dict[str, Any] = {}
    if step_name == "retag_notes":
        m = re.search(mm("regex_retag_total"), text)
        if m:
            out["retag_touched"] = int(m.group(1))
            out["retag_skipped"] = int(m.group(2))
            if m.lastindex and m.lastindex >= 3 and m.group(3) is not None:
                out["retag_llm_fallbacks"] = int(m.group(3))
    elif step_name == "refill_singleton_tags":
        m = re.search(mm("regex_refill_total"), text)
        if m:
            out["refill_touched"] = int(m.group(1))
            out["refill_skipped"] = int(m.group(2))
            out["refill_llm_errors"] = int(m.group(3))
    elif step_name in ("apply_wikilinks_batch", "apply_wikilinks"):
        m = re.search(mm("regex_changed"), text)
        if m:
            out["wikilinks_changed"] = int(m.group(1))
    elif step_name == "reprocess_notes":
        out["reprocess_saved"] = len(re.findall(re.escape(mm("marker_saved")), text))
        out["reprocess_deleted_empty"] = len(
            re.findall(re.escape(mm("marker_deleted_empty")), text)
        )
    elif step_name in ("apply_duplicates", "apply_duplicates_dryrun"):
        out["duplicates_deleted_lines"] = len(
            re.findall(mm("regex_deleted_line"), text, re.MULTILINE)
        )
        m = re.search(mm("regex_dup_freed"), text)
        if m:
            out["duplicates_export_files"] = int(m.group(1))
            out["duplicates_mb_freed"] = float(m.group(2))
    elif step_name == "singleton_tags_report":
        m = re.search(mm("regex_singleton_count"), text)
        if m:
            out["singleton_tag_notes_reported"] = int(m.group(1))
    elif step_name == "sync_hubs":
        out["hubs_writes"] = len(re.findall(r"write:", text))
    return out


def _flatten_run_metrics(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge per-step metrics from one maintenance run."""
    merged: dict[str, Any] = {}
    for s in steps:
        m = s.get("metrics") or {}
        if not isinstance(m, dict):
            continue
        for k, v in m.items():
            if isinstance(v, (int, float)) and k not in {
                "duplicates_mb_freed",
                "duplicates_export_files",
                "duplicates_deleted_lines",
            }:
                merged[k] = merged.get(k, 0) + v
            else:
                merged[k] = v
    return merged


_RUN_SUM_KEYS = frozenset({
    "refill_touched",
    "refill_skipped",
    "refill_llm_errors",
    "retag_touched",
    "retag_skipped",
    "retag_llm_fallbacks",
    "wikilinks_changed",
    "reprocess_saved",
    "reprocess_deleted_empty",
    "duplicates_deleted_lines",
    "duplicates_export_files",
    "duplicates_mb_freed",
    "hubs_writes",
})
_RUN_LAST_KEYS = frozenset({
    "singleton_tag_notes_reported",
})


def merge_run_totals(prev: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """English docstring omitted (see domain_messages.yaml)."""
    out = dict(prev)
    for k, v in new.items():
        if k in _RUN_SUM_KEYS and isinstance(v, (int, float)):
            ov = out.get(k)
            if isinstance(ov, (int, float)):
                out[k] = ov + v
            else:
                out[k] = v
        elif k in _RUN_LAST_KEYS:
            out[k] = v
        elif isinstance(v, (int, float)) and isinstance(out.get(k), (int, float)):
            out[k] = out[k] + v
        else:
            out[k] = v
    return out


def append_daily_record(
    vault: Path,
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    steps: list[dict[str, Any]],
    ok: bool,
    ts_start: str,
    ts_end: str,
) -> None:
    """Module helper (user strings in YAML)."""
    path = history_path(vault)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[Any] = []
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
            if isinstance(data, list):
                existing = data
        except Exception:
            existing = []

    d = date.today().isoformat()
    run_flat = _flatten_run_metrics(steps)

    prev = next((x for x in existing if isinstance(x, dict) and x.get("date") == d), None)

    if prev is None:
        record = {
            "date": d,
            "runs_count": 1,
            "ts_start": ts_start,
            "ts_end": ts_end,
            "ok": bool(ok),
            "before": before,
            "after": after,
            "delta_notes_md_db700": int(after.get("notes_md_db700", 0))
            - int(before.get("notes_md_db700", 0)),
            "delta_bytes_export": int(after.get("bytes_export", 0)) - int(before.get("bytes_export", 0)),
            "run": run_flat,
        }
    else:
        before_first = prev.get("before") if isinstance(prev.get("before"), dict) else before
        after_latest = after
        merged_run = merge_run_totals(prev.get("run") or {}, run_flat)
        ts_s = min(str(prev.get("ts_start") or ts_start), ts_start)
        ts_e = max(str(prev.get("ts_end") or ts_end), ts_end)
        runs_count = int(prev.get("runs_count") or 1) + 1
        ok_all = bool(prev.get("ok")) and bool(ok)
        record = {
            "date": d,
            "runs_count": runs_count,
            "ts_start": ts_s,
            "ts_end": ts_e,
            "ok": ok_all,
            "before": before_first,
            "after": after_latest,
            "delta_notes_md_db700": int(after_latest.get("notes_md_db700", 0))
            - int(before_first.get("notes_md_db700", 0)),
            "delta_bytes_export": int(after_latest.get("bytes_export", 0))
            - int(before_first.get("bytes_export", 0)),
            "run": merged_run,
        }

    existing = [x for x in existing if isinstance(x, dict) and x.get("date") != d]
    existing.append(record)
    existing.sort(key=lambda x: str(x.get("date", "")))
    existing = existing[-800:]

    path.write_text(
        yaml.dump(existing, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def load_history(vault: Path, *, max_rows: int | None = 120) -> list[dict[str, Any]]:
    path = history_path(vault)
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    rows = [x for x in data if isinstance(x, dict)]
    if max_rows is not None:
        rows = rows[-max_rows:]
    return rows


def render_maintenance_charts(vault: Path) -> list[Path]:
    """English docstring omitted (see domain_messages.yaml)."""
    rows = load_history(vault, max_rows=400)
    if len(rows) < 1:
        return []
    rows = rows[-90:]

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []

    dates = [datetime.strptime(str(r["date"]), "%Y-%m-%d").date() for r in rows]
    notes_b = [int((r.get("before") or {}).get("notes_md_db700", 0)) for r in rows]
    notes_a = [int((r.get("after") or {}).get("notes_md_db700", 0)) for r in rows]
    exp_mb = [round(int((r.get("before") or {}).get("bytes_export", 0)) / (1024 * 1024), 2) for r in rows]
    rq = [int((r.get("before") or {}).get("reprocess_eligible", 0)) for r in rows]
    retag = [int((r.get("run") or {}).get("retag_touched", 0) or 0) for r in rows]
    repro_s = [int((r.get("run") or {}).get("reprocess_saved", 0) or 0) for r in rows]
    repro_d = [int((r.get("run") or {}).get("reprocess_deleted_empty", 0) or 0) for r in rows]
    dup_mb = [float((r.get("run") or {}).get("duplicates_mb_freed", 0) or 0) for r in rows]

    out_dir = charts_dir(vault)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "vault_maintenance_dynamics.png"

    from knowledge_bot.i18n.domain_text import maintenance as mm

    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    fig.suptitle(mm("chart_suptitle"), fontsize=12)

    ax = axes[0, 0]
    ax.plot(dates, notes_b, label=mm("chart_notes_before"), marker="o", ms=3, linewidth=1)
    ax.plot(dates, notes_a, label=mm("chart_notes_after"), marker="o", ms=3, linewidth=1)
    ax.set_title(mm("chart_notes_title"))
    ax.legend(fontsize=8)
    ax.tick_params(axis="x", rotation=35, labelsize=7)
    ax.grid(True, alpha=0.3)

    ax = axes[0, 1]
    ax.fill_between(dates, exp_mb, alpha=0.25)
    ax.plot(dates, exp_mb, color="tab:orange", marker="o", ms=3, linewidth=1)
    ax.set_title(mm("chart_export_title"))
    ax.tick_params(axis="x", rotation=35, labelsize=7)
    ax.grid(True, alpha=0.3)

    ax = axes[1, 0]
    ax.plot(dates, rq, color="tab:red", marker="o", ms=3, linewidth=1)
    ax.set_title(mm("chart_queue_title"))
    ax.tick_params(axis="x", rotation=35, labelsize=7)
    ax.grid(True, alpha=0.3)

    ax = axes[1, 1]
    width = 0.22
    x = range(len(dates))
    ax.bar([i - 1.5 * width for i in x], retag, width=width, label="retag")
    ax.bar([i - 0.5 * width for i in x], repro_s, width=width, label=mm("chart_bar_reprocess"))
    ax.bar([i + 0.5 * width for i in x], repro_d, width=width, label=mm("chart_bar_empty"))
    ax.bar([i + 1.5 * width for i in x], dup_mb, width=width, label=mm("chart_bar_dup"))
    ax.set_title(mm("chart_daily_title"))
    ax.set_xticks(list(x))
    ax.set_xticklabels([str(d) for d in dates], rotation=55, ha="right", fontsize=6)
    ax.legend(fontsize=7)
    ax.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return [out_path]


def build_dynamics_markdown_section(vault: Path, *, table_days: int = 14) -> str:
    """Markdown table + chart embed for audit report."""
    from knowledge_bot.i18n.domain_text import maintenance as mm

    paths = render_maintenance_charts(vault)
    rows = load_history(vault, max_rows=table_days)
    hist = history_path(vault).relative_to(vault).as_posix()
    lines: list[str] = [
        mm("report_section"),
        "",
        mm("report_intro", history_path=hist).strip(),
        "",
    ]
    if paths:
        rel = paths[0].relative_to(vault)
        lines.append(f"![[{rel.as_posix()}]]")
        lines.append("")
    else:
        lines.append(mm("report_chart_pending"))
        lines.append("")

    if not rows:
        lines.append(mm("report_no_history"))
        lines.append("")
        return "\n".join(lines)

    lines.append(mm("report_table_days", days=min(table_days, len(rows))))
    lines.append("")
    lines.append(mm("report_table_header"))
    lines.append("|---|:---:|---:|---:|---:|---:|---:|---:|---:|:---:|")
    for r in rows[-table_days:]:
        b = r.get("before") or {}
        a = r.get("after") or {}
        run = r.get("run") or {}
        nb = int(b.get("notes_md_db700", 0))
        na = int(a.get("notes_md_db700", 0))
        exp_b = round(int(b.get("bytes_export", 0)) / (1024 * 1024), 1)
        rqv = int(b.get("reprocess_eligible", 0))
        ok = "✓" if r.get("ok") else "✗"
        nruns = int(r.get("runs_count") or 1)
        lines.append(
            f"| {r.get('date','')} | {nruns} | {nb}→{na} | {exp_b} | {rqv} | "
            f"{int(run.get('retag_touched', 0) or 0)} | "
            f"{int(run.get('reprocess_saved', 0) or 0)} | "
            f"{int(run.get('reprocess_deleted_empty', 0) or 0)} | "
            f"{float(run.get('duplicates_mb_freed', 0) or 0):.1f} | {ok} |"
        )
    lines.append("")
    return "\n".join(lines)
