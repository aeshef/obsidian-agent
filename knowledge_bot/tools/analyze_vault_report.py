#!/usr/bin/env python3
"""Read-only vault audit: tags + duplicates + maintenance sidecar (writes optional report).

  python analyze_vault_report.py
  python analyze_vault_report.py --out reports/vault_audit.md
  PYTHONPATH=../.. python tools/analyze_vault_report.py --vault /path/to/vault --out ...
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AGENT_DIR = SCRIPT_DIR.parent.parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))


def _vault_root(args: argparse.Namespace) -> Path:
    if args.vault:
        return Path(args.vault).expanduser().resolve()
    from knowledge_bot.core.config import load_config

    return load_config().vault_path


def _default_report_rel() -> str:
    from shared.vault_paths_config import dashboards_sub, folder, vault_file

    dash = folder("dashboards")
    charts = dashboards_sub("charts")
    name = vault_file("vault_audit_report_md")
    return f"{dash}/{charts}/{name}"


def _parse_last_maintenance_run(log_path: Path) -> dict | None:
    """Parse last JSON block with 'steps' from vault_write_maintenance.log."""
    if not log_path.exists():
        return None
    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if not text.strip():
        return None

    decoder = json.JSONDecoder()
    last_block: dict | None = None
    i = 0
    n = len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        if text[i] != "{":
            i += 1
            continue
        try:
            obj, end = decoder.raw_decode(text, i)
            if isinstance(obj, dict) and "steps" in obj:
                last_block = obj
            i = end
        except ValueError:
            i += 1
    return last_block


def _format_maintenance_run(run: dict) -> list[str]:
    lines: list[str] = []
    if run.get("skipped"):
        reason = run.get("reason", "?")
        extra = " (day marker written, steps skipped)" if run.get("wrote_marker") else ""
        lines.append(
            f"**Last maintenance run**: skipped — `{reason}`{extra}. "
            "Re-running the same day does not repeat steps (expected)."
        )
        lines.append("")
        return lines

    ok = run.get("ok", True)
    steps = run.get("steps") or []
    lines.append(f"**Last maintenance run** ({'ok' if ok else 'failed'}), {len(steps)} steps:")
    lines.append("")
    step_labels = {
        "sync_hubs": "Hubs (sync_hubs)",
        "apply_wikilinks_batch": "Wikilinks (apply_wikilinks_batch)",
        "retag_notes": "Retag (retag_notes)",
        "reprocess_notes": "Reprocess stems (reprocess_notes)",
        "llm_preflight": "Network / LLM preflight",
        "refill_singleton_tags": "Refill singleton tags",
        "apply_duplicates_dryrun": "Duplicates dry-run",
    }
    if not ok and any(s.get("name") == "llm_preflight" for s in steps):
        lines.append(
            "_If DNS failed at midnight, LLM steps are skipped; note counts may rise from "
            "VPS ingest between runs — not a rollback of prior cleanup._"
        )
        lines.append("")
    for s in steps:
        name = s.get("name", "?")
        rc = s.get("returncode", "?")
        sec = s.get("seconds", 0)
        label = step_labels.get(name, name)
        status = "ok" if rc == 0 else "fail"
        lines.append(f"  - [{status}] **{label}** — {sec:.1f}s")
        stdout = (s.get("stdout_tail") or "").strip()
        if stdout:
            tail = [ln for ln in stdout.splitlines() if ln.strip()][-3:]
            for ln in tail:
                lines.append(f"    > {ln}")
        stderr = (s.get("stderr_tail") or "").strip()
        if stderr:
            err_lines = [ln for ln in stderr.splitlines() if ln.strip() and "NOT available" not in ln]
            for ln in err_lines[-2:]:
                lines.append(f"    ! {ln}")
    return lines


def _build_maintenance_section(vault: Path) -> str:
    import datetime

    import yaml

    from knowledge_bot.services.reprocess_candidates import discover_candidate_paths, load_reprocess_yaml
    from shared.vault_layout import knowledge_subdir
    from shared.vault_paths_config import vault_rel_path

    lines = ["## 3. Daily maintenance (vault_daily_maintenance)", ""]

    kd = knowledge_subdir()
    hubs_rel = vault_rel_path("knowledge_hubs")
    hubs_dir = vault / kd / hubs_rel
    if hubs_dir.exists():
        hubs = sorted(hubs_dir.glob("*.md"))
        lines.append(f"**Hubs** (`{kd}/{hubs_rel}/`): {len(hubs)} files")
        for h in hubs:
            mtime = datetime.datetime.fromtimestamp(h.stat().st_mtime).strftime("%Y-%m-%d")
            try:
                text = h.read_text(encoding="utf-8", errors="ignore")
                link_count = text.count("[[")
                lines.append(f"  - `{h.name}` — {link_count} links (updated {mtime})")
            except OSError:
                lines.append(f"  - `{h.name}` (updated {mtime})")
    else:
        lines.append(f"**Hubs**: `{hubs_rel}/` not created yet (run `sync_hubs.py --apply`)")

    lines.append("")

    tag_cfg_path = Path(__file__).resolve().parent.parent / "config" / "tag_ontology.yaml"
    if tag_cfg_path.exists():
        try:
            tcfg = yaml.safe_load(tag_cfg_path.read_text(encoding="utf-8")) or {}
            mappings = tcfg.get("mappings", {}) or {}
            lines.append(f"**Tag ontology**: {len(mappings)} mappings in `config/tag_ontology.yaml`")
        except OSError:
            lines.append("**Tag ontology**: config read error")
    else:
        lines.append("**Tag ontology**: config not found")

    lines.append("")

    sync_dir = vault / ".sync"
    marker = sync_dir / "daily_vault_write_maintenance_date.txt"
    if marker.exists():
        last_run = marker.read_text(encoding="utf-8").strip()
        lines.append(f"**Last maintenance date marker**: `{last_run}`")
    else:
        lines.append("**Last maintenance date marker**: not set")

    lines.append("")

    last_run_data: dict | None = None
    sidecar = sync_dir / "last_vault_maintenance_run.json"
    if sidecar.exists():
        try:
            raw = json.loads(sidecar.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "steps" in raw:
                last_run_data = raw
        except (OSError, json.JSONDecodeError):
            last_run_data = None

    if last_run_data is None:
        log_candidates: list[Path] = [AGENT_DIR / "planning_bot" / "logs" / "vault_write_maintenance.log"]
        agent_root = os.environ.get("OBSIDIAN_AGENT_ROOT", "").strip()
        if agent_root:
            log_candidates.insert(
                0, Path(agent_root).expanduser() / "planning_bot" / "logs" / "vault_write_maintenance.log"
            )
        for lp in log_candidates:
            last_run_data = _parse_last_maintenance_run(lp)
            if last_run_data:
                break

    if last_run_data:
        lines.extend(_format_maintenance_run(last_run_data))
    else:
        lines.append(
            "**Run details**: no `.sync/last_vault_maintenance_run.json` and no parseable JSON in "
            "`planning_bot/logs/vault_write_maintenance.log`."
        )

    lines.append("")

    agent_config_dir = Path(__file__).resolve().parent.parent / "config"
    rpcfg = load_reprocess_yaml(agent_config_dir)
    all_generic = discover_candidate_paths(vault, rpcfg, skip_if_flag=False)
    eligible = discover_candidate_paths(vault, rpcfg, skip_if_flag=True)
    skipped_ct = len(all_generic) - len(eligible)
    if all_generic:
        lines.append(
            f"**Reprocess queue** (`bad_stem_pattern` in `config/reprocess.yaml`): "
            f"**{len(all_generic)}** total, **{len(eligible)}** without `reprocess_skip`"
            + (f" ({skipped_ct} skipped)" if skipped_ct else "")
        )
        for p in eligible[:8]:
            lines.append(f"  - `{p.relative_to(vault)}`")
        if len(eligible) > 8:
            lines.append(f"  - … and {len(eligible) - 8} more")
        if skipped_ct and not eligible:
            lines.append("  - Queue empty: all matches have `reprocess_skip: true` in frontmatter.")
    else:
        lines.append("**Reprocess queue**: none matched `config/reprocess.yaml`")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Vault audit report (tags + duplicates, read-only)")
    ap.add_argument("--vault", default="", help="Vault root (default: VAULT_PATH from config)")
    ap.add_argument(
        "--out",
        "-o",
        default="",
        help="Report .md path (relative to vault or absolute; default from vault_paths.yaml)",
    )
    args = ap.parse_args()

    vault = _vault_root(args)
    child_env = {
        **os.environ,
        "VAULT_PATH": str(vault),
        "PYTHONPATH": os.pathsep.join(
            [str(AGENT_DIR), os.environ.get("PYTHONPATH", "")]
        ).strip(os.pathsep),
    }

    tags_out = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "analyze_vault_tags.py")],
        cwd=str(SCRIPT_DIR),
        capture_output=True,
        text=True,
        timeout=600,
        env=child_env,
    )
    dups_out = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "analyze_vault_duplicates.py")],
        cwd=str(SCRIPT_DIR),
        capture_output=True,
        text=True,
        timeout=600,
        env=child_env,
    )

    import datetime

    from knowledge_bot.services.maintenance_metrics import build_dynamics_markdown_section
    from shared.vault_layout import knowledge_subdir

    maintenance_section = _build_maintenance_section(vault)
    dynamics_section = build_dynamics_markdown_section(vault)

    report_lines = [
        f"# Vault audit — {knowledge_subdir()}",
        "",
        f"Updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
        "## 1. Tags",
        "",
        "```",
        tags_out.stdout if tags_out.returncode == 0 else tags_out.stderr or "error",
        "```",
        "",
        "---",
        "",
        "## 2. Duplicates (_1, _2, _3)",
        "",
        "```",
        dups_out.stdout if dups_out.returncode == 0 else dups_out.stderr or "error",
        "```",
        "",
        "---",
        "",
        maintenance_section,
        "---",
        "",
        dynamics_section,
    ]

    report_text = "\n".join(report_lines)

    out_arg = (args.out or "").strip() or _default_report_rel()
    out_path = Path(out_arg)
    if not out_path.is_absolute():
        out_path = vault / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_text, encoding="utf-8")
    print(f"Report written: {out_path}")
    if not args.out:
        print(report_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
