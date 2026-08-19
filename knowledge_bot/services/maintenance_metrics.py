"""Vault maintenance snapshots, history YAML, and chart generation."""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

# Line-anchored; scan via splitlines() — do not pass re.M into Pattern.finditer
# (that argument is `pos`, so ^ never matches a marker below the stdout header).
_DELETED_NOTE_RE = re.compile(r"^\s*DELETED_NOTE:\s*(\S+)\s+(.+?)\s*$")
_DELETED_ORIGINAL_RE = re.compile(r"^\s*DELETED_ORIGINAL:\s*(.+?)\s*$")
_DELETED_ORIGINAL_LIST_RE = re.compile(r"^\s*DELETED_ORIGINAL_LIST:\s*(.+?)\s*$")
_EXPORT_SECTION_RE = re.compile(r"^---\s*.*Export")

from knowledge_bot.core.config import load_config
from knowledge_bot.services.reprocess_candidates import (
    discover_candidate_paths,
    load_reprocess_yaml,
)


def history_path(vault: Path) -> Path:
    from shared.vault_paths_config import dashboards_sub, folder

    return vault / folder("dashboards") / dashboards_sub("data") / "vault_maintenance_history.yaml"


def charts_dir(vault: Path) -> Path:
    from shared.chart_paths import chart_path

    return chart_path(vault, "chart_maintenance_dynamics_png").parent


def _legacy_maintenance_chart_name() -> str:
    from shared.vault_paths_config import vault_file

    try:
        return vault_file("legacy_chart_maintenance_dynamics_png")
    except KeyError:
        return "vault_maintenance_dynamics.png"


def cleanup_legacy_maintenance_chart(vault: Path) -> bool:
    """Remove flat charts-root PNG superseded by the localized maintenance chart path."""
    from shared.chart_paths import charts_root

    legacy = charts_root(vault) / _legacy_maintenance_chart_name()
    if legacy.is_file():
        try:
            legacy.unlink()
            return True
        except OSError:
            return False
    return False


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
    untagged = 0
    try:
        from knowledge_bot.services.untagged_notes import count_untagged_notes

        untagged = count_untagged_notes(vault)
    except Exception:
        pass
    return {
        "notes_md_db700": notes_all,
        "notes_md_excl_export": notes_no_exp,
        "bytes_db700": _dir_size(db),
        "bytes_export": _dir_size(exp),
        "reprocess_total": len(discover_candidate_paths(vault, rpcfg, skip_if_flag=False)),
        "reprocess_eligible": len(discover_candidate_paths(vault, rpcfg, skip_if_flag=True)),
        "notes_without_tags": untagged,
    }


def extract_step_metrics(step_name: str, stdout: str, stderr: str = "") -> dict[str, Any]:
    """Parse numeric totals from maintenance step stdout/stderr."""
    from knowledge_bot.i18n.domain_text import maintenance as mm

    text = stdout or ""
    if not text.strip() and not (stderr or "").strip():
        return {}
    out: dict[str, Any] = {}
    if step_name in ("retag_notes", "retag_untagged"):
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
        from shared.domain_messages import dmsg

        applied = re.findall(mm("regex_deleted_line"), text, re.MULTILINE)
        dry_marker = mm("dup_delete_marker") or dmsg(
            "knowledge_vault_runner", "dup_delete_marker", default=""
        )
        dry = (
            re.findall(rf"^\s*{re.escape(dry_marker)}", text, re.MULTILINE)
            if dry_marker
            else []
        )
        out["duplicates_deleted_lines"] = len(applied) + len(dry)
        m = re.search(mm("regex_dup_freed"), text)
        if m:
            out["duplicates_export_files"] = int(m.group(1))
            out["duplicates_mb_freed"] = float(m.group(2))
    elif step_name == "export_orphans":
        m = re.search(mm("regex_export_orphans_summary"), text)
        if m:
            out["export_orphans_found"] = int(m.group(1))
            out["export_orphans_bytes"] = int(m.group(2))
            out["export_referenced_files"] = int(m.group(3))
            out["export_total_files"] = int(m.group(4))
        m = re.search(mm("regex_export_broken_refs"), text)
        if m:
            out["export_broken_refs"] = int(m.group(1))
        m = re.search(mm("regex_export_rehydrated_total"), text)
        if m:
            out["export_rehydrated"] = int(m.group(1))
        m = re.search(mm("regex_export_deleted_total"), text)
        if m:
            out["export_orphans_deleted"] = int(m.group(1))
            out["export_orphans_deleted_bytes"] = int(m.group(2))
        m = re.search(mm("regex_export_broken_refs_cleaned"), text)
        if m:
            out["export_broken_refs_cleaned_notes"] = int(m.group(1))
        m = re.search(mm("regex_export_broken_body_refs_cleaned"), text)
        if m:
            out["export_broken_body_refs_cleaned_notes"] = int(m.group(1))
    elif step_name == "singleton_tags_report":
        m = re.search(mm("regex_singleton_count"), text)
        if m:
            out["singleton_tag_notes_reported"] = int(m.group(1))
    elif step_name == "sync_hubs":
        out["hubs_writes"] = len(re.findall(r"write:", text))
    deleted = extract_deleted_paths_from_stdout(step_name, text)
    if deleted:
        out["deleted_paths"] = deleted
        if step_name == "apply_duplicates":
            out["duplicates_notes_deleted"] = sum(
                1 for d in deleted if d.get("reason") == "duplicate"
            )
    return out


def _is_note_path(path: str) -> bool:
    return path.strip().lower().endswith(".md")


def _deleted_line_re() -> re.Pattern[str]:
    from knowledge_bot.i18n.domain_text import maintenance as mm

    return re.compile(rf"{mm('regex_deleted_line')}\s*(.+?)(?:\s+#.*)?\s*$")


def extract_deleted_paths_from_stdout(step_name: str, stdout: str) -> list[dict[str, str]]:
    """Parse deleted vault-relative paths from maintenance step stdout."""
    if not stdout:
        return []
    out: list[dict[str, str]] = []
    deleted_line_re = _deleted_line_re()
    if step_name == "reprocess_notes":
        seen: set[str] = set()
        for line in stdout.splitlines():
            m_note = _DELETED_NOTE_RE.match(line)
            if m_note:
                path = m_note.group(2).strip()
                if path and path not in seen:
                    seen.add(path)
                    out.append({"path": path, "reason": m_note.group(1).strip()})
                continue
            m_orig = _DELETED_ORIGINAL_RE.match(line)
            if m_orig:
                path = m_orig.group(1).strip()
                if path and path not in seen:
                    seen.add(path)
                    out.append({"path": path, "reason": "reprocess_relocated"})
                continue
            m_list = _DELETED_ORIGINAL_LIST_RE.match(line)
            if m_list:
                for path in m_list.group(1).split("\t"):
                    path = path.strip()
                    if path and path not in seen:
                        seen.add(path)
                        out.append({"path": path, "reason": "reprocess_relocated"})
        return out
    if step_name == "export_orphans":
        for line in stdout.splitlines():
            m = deleted_line_re.match(line)
            if not m:
                continue
            path = m.group(1).strip()
            if path:
                out.append({"path": path, "reason": "export_orphan"})
        return out
    if step_name != "apply_duplicates":
        return out
    in_export = False
    for line in stdout.splitlines():
        if _EXPORT_SECTION_RE.match(line.strip()):
            in_export = True
            continue
        m = deleted_line_re.match(line)
        if not m:
            continue
        path = m.group(1).strip()
        if in_export or not _is_note_path(path):
            reason = "export_orphan"
        else:
            reason = "duplicate"
        out.append({"path": path, "reason": reason})
    return out


def collect_deletions_from_steps(steps: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Merge deleted path entries from all maintenance steps (unique by path).

    Falls back to stdout/stdout_tail so relocated originals still enter the
    5b.2c manifest when step metrics omitted them.
    """
    seen: set[str] = set()
    merged: list[dict[str, str]] = []
    for step in steps:
        name = str(step.get("name") or "")
        metrics = step.get("metrics") if isinstance(step.get("metrics"), dict) else {}
        raw = metrics.get("deleted_paths") if isinstance(metrics, dict) else None
        items: list[Any] = list(raw) if isinstance(raw, list) else []
        stdout = str(step.get("stdout_tail") or step.get("stdout") or "")
        if stdout:
            items.extend(extract_deleted_paths_from_stdout(name, stdout))
        for item in items:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            reason = str(item.get("reason") or "unknown").strip()
            if not path or path in seen:
                continue
            seen.add(path)
            merged.append({"path": path, "reason": reason})
    return merged


def write_deletion_manifest(sync_dir: Path, deletions: list[dict[str, str]], ts: str) -> None:
    """Write `.sync/last_maintenance_deleted_paths.json` for audit and VPS cleanup (5b.2c)."""
    sync_dir.mkdir(parents=True, exist_ok=True)
    by_reason: dict[str, int] = {}
    for item in deletions:
        reason = str(item.get("reason") or "unknown")
        by_reason[reason] = by_reason.get(reason, 0) + 1
    payload = {
        "ts": ts,
        "deleted": deletions,
        "summary": by_reason,
    }
    (sync_dir / "last_maintenance_deleted_paths.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_maintenance_run_sidecar(sync_dir: Path, out: dict[str, Any]) -> None:
    """Persist last run JSON for vault audit §3 (steps + deletions)."""
    sync_dir.mkdir(parents=True, exist_ok=True)
    sidecar = dict(out)
    sidecar["deleted"] = collect_deletions_from_steps(out.get("steps") or [])
    (sync_dir / "last_vault_maintenance_run.json").write_text(
        json.dumps(sidecar, ensure_ascii=False, default=str, indent=2),
        encoding="utf-8",
    )


def refresh_sidecar_from_maintenance_log(vault: Path, sync_dir: Path) -> bool:
    """Rebuild sidecar from the latest JSON block in vault_write_maintenance.log."""
    from knowledge_bot.services.vault_audit.report import _parse_last_maintenance_run

    agent_root = Path(__file__).resolve().parent.parent.parent
    candidates = [
        agent_root / "planning_bot" / "logs" / "vault_write_maintenance.log",
    ]
    runtime_root = os.environ.get("OBSIDIAN_AGENT_RUNTIME_ROOT", "").strip()
    if runtime_root:
        candidates.insert(
            0,
            Path(runtime_root) / "agent" / "planning_bot" / "logs" / "vault_write_maintenance.log",
        )
    obs_root = os.environ.get("OBSIDIAN_AGENT_ROOT", "").strip()
    if obs_root:
        candidates.insert(
            0,
            Path(obs_root).expanduser() / "planning_bot" / "logs" / "vault_write_maintenance.log",
        )
    for lp in candidates:
        run = _parse_last_maintenance_run(lp)
        if run and isinstance(run, dict) and run.get("steps"):
            write_maintenance_run_sidecar(sync_dir, run)
            return True
    return False


def _merge_deleted_entries(
    prev: list[Any] | None, new: list[dict[str, str]], *, cap: int = 40
) -> list[dict[str, str]]:
    seen: set[str] = set()
    merged: list[dict[str, str]] = []
    for item in list(prev or []) + list(new):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        reason = str(item.get("reason") or "unknown").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        merged.append({"path": path, "reason": reason})
        if len(merged) >= cap:
            break
    return merged


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
                "duplicates_notes_deleted",
            }:
                merged[k] = merged.get(k, 0) + v
            elif k == "deleted_paths" and isinstance(v, list):
                merged[k] = _merge_deleted_entries(merged.get(k), v, cap=100)
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
    "duplicates_notes_deleted",
    "duplicates_export_files",
    "duplicates_mb_freed",
    "export_orphans_found",
    "export_orphans_deleted",
    "export_orphans_deleted_bytes",
    "export_broken_refs",
    "export_broken_refs_cleaned_notes",
    "export_broken_body_refs_cleaned_notes",
    "export_rehydrated",
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

    d = ts_start[:10] if len(ts_start) >= 10 else date.today().isoformat()
    run_flat = _flatten_run_metrics(steps)
    deleted_entries = _merge_deleted_entries(
        (run_flat.get("deleted_paths") if isinstance(run_flat.get("deleted_paths"), list) else None),
        collect_deletions_from_steps(steps),
    )
    if deleted_entries:
        run_flat["deleted_paths"] = deleted_entries

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
            "deleted_notes": deleted_entries,
        }
    else:
        before_first = prev.get("before") if isinstance(prev.get("before"), dict) else before
        after_latest = after
        merged_run = merge_run_totals(prev.get("run") or {}, run_flat)
        if deleted_entries:
            merged_run["deleted_paths"] = _merge_deleted_entries(
                merged_run.get("deleted_paths") if isinstance(merged_run.get("deleted_paths"), list) else None,
                deleted_entries,
            )
        merged_deleted = _merge_deleted_entries(prev.get("deleted_notes"), deleted_entries)
        ts_s = min(str(prev.get("ts_start") or ts_start), ts_start)
        ts_e = max(str(prev.get("ts_end") or ts_end), ts_end)
        runs_count = int(prev.get("runs_count") or 1) + 1
        # Latest run wins: manual FORCE rerun after a failed nightly should show ✓ for the day.
        ok_latest = bool(ok)
        record = {
            "date": d,
            "runs_count": runs_count,
            "ts_start": ts_s,
            "ts_end": ts_e,
            "ok": ok_latest,
            "before": before_first,
            "after": after_latest,
            "delta_notes_md_db700": int(after_latest.get("notes_md_db700", 0))
            - int(before_first.get("notes_md_db700", 0)),
            "delta_bytes_export": int(after_latest.get("bytes_export", 0))
            - int(before_first.get("bytes_export", 0)),
            "run": merged_run,
            "deleted_notes": merged_deleted,
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

    from knowledge_bot.i18n.domain_text import maintenance as mm
    from shared.chart_paths import chart_path, ensure_parent

    out_path = chart_path(vault, "chart_maintenance_dynamics_png")
    ensure_parent(out_path)
    cleanup_legacy_maintenance_chart(vault)

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


def build_dynamics_markdown_section(
    vault: Path, *, table_days: int = 14, include_deletions: bool = True
) -> str:
    """Callout history + chart embed for audit report (no pipe tables)."""
    from knowledge_bot.i18n.domain_text import maintenance as mm

    paths = render_maintenance_charts(vault)
    rows = load_history(vault, max_rows=table_days)
    hist = history_path(vault).relative_to(vault).as_posix()
    lines: list[str] = [
        mm("report_section"),
        "",
        mm("report_dynamics_open"),
        mm("report_dynamics_hist", history_path=hist),
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

    shown = rows[-table_days:]
    lines.append(mm("report_days_fold", days=len(shown)))
    for r in shown:
        run = r.get("run") or {}
        delta = int(r.get("delta_notes_md_db700", 0))
        dup_notes = int(run.get("duplicates_notes_deleted", 0) or 0)
        if dup_notes == 0 and run.get("duplicates_deleted_lines"):
            dup_notes = max(
                0,
                int(run.get("duplicates_deleted_lines", 0))
                - int(run.get("reprocess_deleted_empty", 0) or 0),
            )
        repr_empty = int(run.get("reprocess_deleted_empty", 0) or 0)
        retag = int(run.get("retag_touched", 0) or 0)
        repr_ok = int(run.get("reprocess_saved", 0) or 0)
        ok = "✓" if r.get("ok") else "✗"
        delta_s = f"{delta:+d}" if delta else "0"
        lines.append(
            mm(
                "report_day_line",
                date=r.get("date", ""),
                runs=int(r.get("runs_count") or 1),
                delta=delta_s,
                dup=dup_notes,
                empty=repr_empty,
                retag=retag,
                repr_ok=repr_ok,
                ok=ok,
            )
        )
    lines.append("")
    if not include_deletions:
        return "\n".join(lines)

    latest_history_date = str(rows[-1].get("date") or "").strip()
    manifest = vault / ".sync" / "last_maintenance_deleted_paths.json"
    if manifest.is_file():
        try:
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            deleted = raw.get("deleted") if isinstance(raw, dict) else []
            ts = str(raw.get("ts") or "").strip()
            manifest_date = ts[:10] if len(ts) >= 10 else ""
            if isinstance(deleted, list) and deleted and manifest_date == latest_history_date:
                lines.append(mm("report_last_deletions_header", ts=ts or "—"))
                lines.append("")
                for item in deleted[:15]:
                    if not isinstance(item, dict):
                        continue
                    path = str(item.get("path") or "").strip()
                    reason = str(item.get("reason") or "?").strip()
                    if path:
                        lines.append(f"- `{path}` — {reason}")
                if len(deleted) > 15:
                    lines.append(mm("report_last_deletions_more", count=len(deleted) - 15))
                lines.append("")
        except (OSError, json.JSONDecodeError):
            pass
    return "\n".join(lines)
