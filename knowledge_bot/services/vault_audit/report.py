"""Assemble vault audit markdown (tags tracked; duplicates via optional maintainer scripts)."""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from knowledge_bot.i18n.domain_text import vault_audit as va
from knowledge_bot.services.maintenance_metrics import build_dynamics_markdown_section
from knowledge_bot.services.reprocess_candidates import discover_candidate_paths, load_reprocess_yaml
from knowledge_bot.services.vault_audit.tags import render_tags_markdown
from shared.vault_layout import knowledge_subdir
from shared.vault_paths_config import folder, vault_file, vault_rel_path

_KB_ROOT = Path(__file__).resolve().parent.parent.parent
_TOOLS = _KB_ROOT / "tools"


def _is_noisy_stderr_line(line: str) -> bool:
    """Hide known macOS media-library warnings from human-facing audit reports."""
    return (
        line.startswith("objc[")
        and "Class AVF" in line
        and "is implemented in both" in line
    )


def _default_report_rel() -> str:
    dash = folder("dashboards")
    name = vault_file("vault_audit_report_md")
    return f"{dash}/{name}"


def _run_maintainer_script(name: str, vault: Path, *, timeout: int = 600) -> str:
    tool = _TOOLS / name
    if not tool.is_file():
        return va("tool_missing", script=name, path=str(tool))
    env = {
        **os.environ,
        "VAULT_PATH": str(vault),
        "PYTHONPATH": os.pathsep.join(
            [str(_KB_ROOT.parent), os.environ.get("PYTHONPATH", "")]
        ).strip(os.pathsep),
    }
    proc = subprocess.run(
        [sys.executable, str(tool)],
        cwd=str(_TOOLS),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if proc.returncode == 0:
        return proc.stdout or ""
    return proc.stderr or proc.stdout or va("tool_error", script=name, code=proc.returncode)


def _parse_last_maintenance_run(log_path: Path) -> dict | None:
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
        reason = run.get("skip_reason") or run.get("reason") or "?"
        extra = va("maint_run_skipped_marker") if run.get("wrote_marker") else ""
        lines.append(va("maint_run_skipped", reason=reason, extra=extra))
        lines.append("")
        return lines

    ok = run.get("ok", True)
    steps = run.get("steps") or []
    fail_n = sum(1 for s in steps if s.get("returncode", 0) != 0)
    ok_n = len(steps) - fail_n
    deleted = run.get("deleted") if isinstance(run.get("deleted"), list) else []
    callout = "failure" if fail_n else "success"
    title = va("hero_title_fail" if fail_n else "hero_title_ok")
    lines.extend(
        [
            va("hero_open"),
            title,
            va("hero_meta", ok=ok_n, fail=fail_n, deleted=len(deleted)),
            "",
            va(
                "maint_run_header",
                callout=callout,
                status=va("status_ok" if ok and not fail_n else "status_fail"),
                count=len(steps),
            ),
            "",
        ]
    )
    step_keys = {
        "sync_hubs": "step_sync_hubs",
        "apply_wikilinks_batch": "step_apply_wikilinks",
        "retag_notes": "step_retag",
        "retag_untagged": "step_retag_untagged",
        "reprocess_notes": "step_reprocess",
        "sanitize_malformed_tags": "step_sanitize_tags",
        "llm_preflight": "step_llm_preflight",
        "refill_singleton_tags": "step_refill_singleton",
        "apply_duplicates_dryrun": "step_dup_dryrun",
        "apply_duplicates": "step_dup_apply",
        "export_orphans": "step_export_orphans",
    }
    if not ok and any(s.get("name") == "llm_preflight" for s in steps):
        lines.append(va("maint_llm_dns_note"))
        lines.append("")

    fold_kind = "failure" if fail_n else "success"
    lines.append(
        f"> [!{fold_kind}]- " + va("maint_steps_fold", count=len(steps))
    )
    for s in steps:
        name = s.get("name", "?")
        rc = s.get("returncode", "?")
        sec = float(s.get("seconds", 0) or 0)
        label = va(step_keys.get(name, "step_unknown"), step=name)
        key = "maint_step_ok_line" if rc == 0 else "maint_step_fail_line"
        lines.append("> " + va(key, label=label, seconds=f"{sec:.1f}"))
        stdout = (s.get("stdout_tail") or "").strip()
        if stdout:
            tail = [ln for ln in stdout.splitlines() if ln.strip()][-2:]
            if tail:
                snippet = tail[-1][:120].strip()
                lines.append("> " + va("maint_step_detail", snippet=snippet))
        stderr = (s.get("stderr_tail") or "").strip()
        if stderr:
            err_lines = [
                ln
                for ln in stderr.splitlines()
                if ln.strip()
                and "NOT available" not in ln
                and not _is_noisy_stderr_line(ln.strip())
            ]
            for ln in err_lines[-1:]:
                snippet = ln[:120].strip()
                lines.append("> " + va("maint_step_warn_detail", snippet=snippet))
    lines.append("")
    return lines


def _format_duplicates_section(raw: str) -> str:
    """Structured callouts only — no ASCII fences (Dataview treats ==== as fields)."""
    import re

    text = raw or ""

    def _int(pat: str, default: int = 0) -> int:
        m = re.search(pat, text, re.I | re.M)
        return int(m.group(1)) if m else default

    # Anchor on ": <n>" so we never grab the "2" inside "(≥2 notes)" or "700_" folder names.
    total = _int(rf"(?:Total notes|{re.escape(va('dups_parse_total'))})[^:\n]*:\s*(\d+)")
    suffix = _int(rf"(?:suffix _N|{re.escape(va('dups_parse_suffix'))})[^:\n]*:\s*(\d+)")
    groups = _int(rf"(?:duplicate groups|{re.escape(va('dups_parse_groups'))})[^:\n]*:\s*(\d+)")
    generic = _int(rf"(?:generic series|{re.escape(va('dups_parse_generic'))})[^:\n]*:\s*(\d+)")
    content = _int(rf"(?:content duplicates|{re.escape(va('dups_parse_content'))})[^:\n]*:\s*(\d+)")

    lines: list[str] = [
        va("dups_abstract_open"),
        va("dups_abstract_head", groups=groups),
        va(
            "dups_abstract_meta",
            total=total or "—",
            suffix=suffix,
            generic=generic,
            content=content,
        ),
        "",
    ]
    if groups == 0:
        extra = va("dups_clean_suffix_note", suffix=suffix) if suffix else ""
        if extra and not extra.startswith(" "):
            extra = " " + extra
        lines.extend(
            [
                va("dups_clean_open"),
                va("dups_clean_body", extra=extra),
                "",
            ]
        )
    else:
        lines.extend(
            [
                va("dups_warn_open"),
                va("dups_warn_body", generic=generic, content=content),
                "",
            ]
        )
    none_token = (va("dups_none_token") or "").strip().lower()
    if "(none)" in text.lower() or (none_token and none_token in text.lower()):
        lines.extend([va("dups_trash_ok_open"), va("dups_trash_ok_body"), ""])
    return "\n".join(lines)



def build_maintenance_section(vault: Path) -> str:
    lines = [va("section_maintenance"), ""]

    kd = knowledge_subdir()
    hubs_rel = vault_rel_path("knowledge_hubs")
    hubs_dir = vault / kd / hubs_rel
    if hubs_dir.exists():
        hubs = sorted(hubs_dir.glob("*.md"))
        lines.append(va("maint_hubs_ok_open", path=f"{kd}/{hubs_rel}"))
        lines.append(va("maint_hubs_ok_head", count=len(hubs)))
        for h in hubs:
            mtime = datetime.datetime.fromtimestamp(h.stat().st_mtime).strftime("%Y-%m-%d")
            try:
                htext = h.read_text(encoding="utf-8", errors="ignore")
                link_count = htext.count("[[")
                lines.append(va("maint_hub_callout_row", name=h.name, links=link_count, mtime=mtime))
            except OSError:
                lines.append(va("maint_hub_callout_row_short", name=h.name, mtime=mtime))
        lines.append("")
    else:
        lines.extend([va("maint_hubs_warn_open"), va("maint_hubs_warn_body", hubs_rel=hubs_rel), ""])

    tag_cfg_path = _KB_ROOT / "config" / "tag_ontology.yaml"
    if tag_cfg_path.exists():
        try:
            tcfg = yaml.safe_load(tag_cfg_path.read_text(encoding="utf-8")) or {}
            mappings = tcfg.get("mappings", {}) or {}
            if len(mappings) == 0:
                lines.append(va("maint_ontology_zero").rstrip())
            else:
                lines.append(va("maint_ontology_ok", count=len(mappings)).rstrip())
        except OSError:
            lines.append(va("maint_ontology_error").rstrip())
    else:
        lines.append(va("maint_ontology_missing").rstrip())

    lines.append("")
    sync_dir = vault / ".sync"
    marker = sync_dir / "daily_vault_write_maintenance_date.txt"
    if marker.exists():
        last_run = marker.read_text(encoding="utf-8").strip()
        lines.append(va("maint_marker", date=last_run).rstrip())
    else:
        lines.append(va("maint_marker_missing").rstrip())

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
        log_candidates: list[Path] = [_KB_ROOT.parent / "planning_bot" / "logs" / "vault_write_maintenance.log"]
        agent_root = os.environ.get("OBSIDIAN_AGENT_ROOT", "").strip()
        if agent_root:
            log_candidates.insert(
                0,
                Path(agent_root).expanduser() / "planning_bot" / "logs" / "vault_write_maintenance.log",
            )
        for lp in log_candidates:
            last_run_data = _parse_last_maintenance_run(lp)
            if last_run_data:
                break

    if last_run_data:
        lines.extend(_format_maintenance_run(last_run_data))
        deleted = last_run_data.get("deleted")
        if isinstance(deleted, list) and deleted:
            from knowledge_bot.i18n.domain_text import maintenance as mm

            ts = str(last_run_data.get("ts_end") or last_run_data.get("ts") or "—")
            lines.append("")
            lines.append(va("maint_deletions_ok").rstrip())
            lines.append("")
            lines.append(va("maint_deleted_paths_open", ts=ts))
            for item in deleted[:12]:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or "").strip()
                reason = str(item.get("reason") or "?").strip()
                if path:
                    tag = "duplicate" if "dup" in reason.lower() else reason
                    lines.append(f"> - 🟡 `{path}` — {tag}")
            if len(deleted) > 12:
                lines.append(va("maint_deleted_paths_more", count=len(deleted) - 12))
            lines.append("")
    else:
        lines.append(va("maint_run_details_missing"))

    lines.append("")
    agent_config_dir = _KB_ROOT / "config"
    rpcfg = load_reprocess_yaml(agent_config_dir)
    all_generic = discover_candidate_paths(vault, rpcfg, skip_if_flag=False)
    eligible = discover_candidate_paths(vault, rpcfg, skip_if_flag=True)
    skipped_ct = len(all_generic) - len(eligible)
    if all_generic:
        kind = "warning" if eligible else "success"
        lines.extend(
            [
                va(
                    "maint_reprocess_queue_open",
                    kind=kind,
                ),
                va(
                    "maint_reprocess_queue_body",
                    total=len(all_generic),
                    eligible=len(eligible),
                    skip=f" · skip {skipped_ct}" if skipped_ct else "",
                ),
                # Keep callout continuous: a bare "" ends the block in Obsidian.
                ">",
            ]
        )
        for p in eligible[:8]:
            lines.append(va("maint_reprocess_row", path=p.relative_to(vault).as_posix()))
        if len(eligible) > 8:
            lines.append(va("maint_reprocess_more_callout", count=len(eligible) - 8))
        if skipped_ct and not eligible:
            lines.append(va("maint_reprocess_all_skipped"))
        lines.append("")
    else:
        lines.extend(
            [
                va("maint_reprocess_empty_open"),
                va("maint_reprocess_empty_body"),
                "",
            ]
        )

    return "\n".join(lines)


def build_vault_audit_report(vault: Path) -> str:
    kd = knowledge_subdir()
    tags_md = render_tags_markdown(vault)
    dups_raw = _run_maintainer_script("analyze_vault_duplicates.py", vault)
    dups_md = _format_duplicates_section(dups_raw)
    maintenance_section = build_maintenance_section(vault)
    dynamics_section = build_dynamics_markdown_section(vault, include_deletions=False)

    return "\n".join(
        [
            va("report_title", knowledge_dir=kd),
            "",
            va("report_updated_callout"),
            va("report_updated_body", timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
            "",
            "---",
            "",
            va("section_tags"),
            "",
            tags_md.rstrip(),
            "",
            "---",
            "",
            va("section_duplicates"),
            "",
            dups_md.rstrip(),
            "",
            "---",
            "",
            maintenance_section.rstrip(),
            "",
            "---",
            "",
            dynamics_section.rstrip(),
            "",
        ]
    )


def write_vault_audit_report(vault: Path, out_path: Path | None = None) -> Path:
    rel = _default_report_rel()
    target = out_path or (vault / rel)
    if not target.is_absolute():
        target = vault / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_vault_audit_report(vault), encoding="utf-8")
    return target
