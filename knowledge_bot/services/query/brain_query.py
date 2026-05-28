from __future__ import annotations

import json
import logging
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from knowledge_bot.core.llm import LLMClient
from knowledge_bot.core.settings import load_prompt
from knowledge_bot.services.query.history import append_turn, format_history_for_prompt, load_history
from knowledge_bot.services.query.index_builder import build_or_refresh_index, load_index

log = logging.getLogger("kb.query.brain")


@dataclass
class BrainQueryResult:
    text: str
    # list of (vault_rel_path, note_title) for existing media files
    media_files: list[tuple[str, str]] = field(default_factory=list)

def _base_prefix() -> str:
    from shared.vault_layout import knowledge_index_prefix

    return knowledge_index_prefix()


def _compact_catalog_max_chars() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int(
        "knowledge_query",
        "compact_catalog_max_chars",
        env="KNOWLEDGE_COMPACT_CATALOG_MAX_CHARS",
        default=220000,
    )


def _catalog_snippet_chars() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int(
        "knowledge_query",
        "catalog_snippet_chars",
        env="KNOWLEDGE_CATALOG_SNIPPET_CHARS",
        default=120,
    )


def _preselect_max() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int(
        "knowledge_query", "preselect_max", env="KNOWLEDGE_PRESELECT_MAX", default=40
    )


def _select_candidates_max() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int(
        "knowledge_query",
        "select_candidates_max",
        env="KNOWLEDGE_SELECT_CANDIDATES_MAX",
        default=40,
    )


def _select_max_tokens() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int(
        "knowledge_query",
        "select_max_tokens",
        env="KNOWLEDGE_QUERY_SELECT_MAX_TOKENS",
        default=1024,
    )


def _preselect_max_tokens() -> int:
    from shared.agent.platform_config import platform_int

    base = platform_int(
        "knowledge_query",
        "preselect_max_tokens",
        env="KNOWLEDGE_PRESELECT_MAX_TOKENS",
        default=2048,
    )
    return min(base, _preselect_max() * 48 + 256)


def _max_selected_paths() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int(
        "knowledge_query",
        "max_selected_notes",
        env="KNOWLEDGE_MAX_SELECTED_NOTES",
        default=14,
    )


def _answer_timeout() -> float:
    from shared.agent.platform_config import platform_float

    return platform_float(
        "knowledge_query",
        "answer_timeout_sec",
        env="KNOWLEDGE_QUERY_ANSWER_TIMEOUT_SEC",
        default=300.0,
    )


def _answer_temperature() -> float:
    from shared.agent.platform_config import platform_float

    return platform_float(
        "knowledge_query",
        "answer_temperature",
        env="KNOWLEDGE_QUERY_ANSWER_TEMPERATURE",
        default=0.3,
    )


def _preselect_timeout() -> float:
    from shared.agent.platform_config import platform_float

    return platform_float(
        "knowledge_query",
        "preselect_timeout_sec",
        env="KNOWLEDGE_QUERY_PRESELECT_TIMEOUT_SEC",
        default=120.0,
    )


def _select_timeout() -> float:
    from shared.agent.platform_config import platform_float

    return platform_float(
        "knowledge_query",
        "select_timeout_sec",
        env="KNOWLEDGE_QUERY_SELECT_TIMEOUT_SEC",
        default=60.0,
    )


def _build_compact_catalog(entries: list[dict[str, Any]]) -> tuple[str, dict[str, str]]:
    """Module helper (user strings in YAML)."""
    lines: list[str] = []
    short_to_full: dict[str, str] = {}
    total_chars = 0
    snip_cap = _catalog_snippet_chars()

    for e in entries:
        rel = e.get("rel_path", "")
        prefix = _base_prefix()
        short = rel[len(prefix) :] if prefix and rel.startswith(prefix) else rel
        title = (e.get("title") or "").strip()
        tags = ",".join(e.get("tags") or [])
        raw_snip = (e.get("summary") or e.get("preview") or "").strip().replace("\n", " ")
        snip = raw_snip[:snip_cap] if raw_snip else ""
        if snip:
            line = f"{short}|{title}|{tags}|{snip}" if tags else f"{short}|{title}||{snip}"
        else:
            line = f"{short}|{title}|{tags}" if tags else f"{short}|{title}"
        if total_chars + len(line) + 1 > _compact_catalog_max_chars():
            log.warning("compact catalog truncated at %d/%d entries", len(lines), len(entries))
            break
        lines.append(line)
        short_to_full[short] = rel
        total_chars += len(line) + 1

    log.info("compact catalog: %d entries, %d chars", len(lines), total_chars)
    return "\n".join(lines), short_to_full


def _llm_json_failed(raw: Any) -> bool:
    return isinstance(raw, dict) and raw.get("_llm_error") == "json_parse"


def _path_item_to_str(item: Any) -> str | None:
    if isinstance(item, str):
        return item.strip() or None
    if isinstance(item, dict):
        for key in ("path", "rel_path", "short_path", "short", "id"):
            v = item.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def _parse_preselect(raw: Any, short_to_full: dict[str, str]) -> list[str]:
    """English docstring omitted (see domain_messages.yaml)."""
    if isinstance(raw, dict):
        raw = raw.get("candidates") or raw.get("paths") or raw.get("notes") or []
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        s = _path_item_to_str(item)
        if not s:
            continue
        if s in short_to_full and s not in seen:
            result.append(short_to_full[s])
            seen.add(s)
            continue
        prefix = _base_prefix()
        short = s[len(prefix) :] if prefix and s.startswith(prefix) else s
        if short in short_to_full and short not in seen:
            result.append(short_to_full[short])
            seen.add(short)
    return result[: _preselect_max()]


def _build_summary_catalog(candidates: list[dict[str, Any]]) -> str:
    """English docstring omitted (see domain_messages.yaml)."""
    blocks: list[str] = []
    for e in candidates:
        tags = ", ".join(e.get("tags") or [])
        summ = (e.get("summary") or "").strip()[:500]
        prev = (e.get("preview") or "").strip()[:1200]
        block = f"PATH: {e['rel_path']}\nTITLE: {e.get('title', '')}\nTAGS: {tags}"
        if summ:
            block += f"\nSUMMARY: {summ}"
        if prev:
            block += f"\nPREVIEW: {prev}"
        blocks.append(block)
    return "\n\n---\n\n".join(blocks)


def _normalize_select_result(raw: Any, valid_paths: set[str]) -> list[str]:
    if isinstance(raw, dict):
        raw = raw.get("paths") or raw.get("rel_paths") or raw.get("notes")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item in valid_paths and item not in seen:
            out.append(item)
            seen.add(item)
        elif isinstance(item, dict):
            rp = item.get("rel_path") or item.get("path")
            if isinstance(rp, str) and rp in valid_paths and rp not in seen:
                out.append(rp)
                seen.add(rp)
    return out[:_max_selected_paths()]


def _safe_note_path(vault: Path, rel: str) -> Path | None:
    if not rel or ".." in Path(rel).parts:
        return None
    p = (vault / rel).resolve()
    try:
        p.relative_to(vault.resolve())
    except ValueError:
        return None
    return p if p.is_file() else None


_MEDIA_EXTENSIONS = frozenset(
    ".mp4 .mov .avi .mkv .webm .jpg .jpeg .png .gif .webp .pdf .mp3 .ogg .m4a".split()
)
def _max_media_per_query() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int(
        "knowledge_query",
        "max_media_per_query",
        env="KNOWLEDGE_MAX_MEDIA_PER_QUERY",
        default=6,
    )


def _strip_file_sections(note_text: str) -> str:
    """English docstring omitted (see domain_messages.yaml)."""
    from shared.vault_layout import knowledge_subdir

    sub = knowledge_subdir()
    media_ext = (".mp4", ".mov", ".avi", ".mkv", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".mp3")
    out: list[str] = []
    in_fm = note_text.startswith("---")
    skip_files_block = False
    for line in note_text.splitlines():
        if in_fm:
            if line.strip().startswith("files:") or line.strip().startswith('"files"'):
                skip_files_block = True
                continue
            if skip_files_block:
                if line.startswith(" ") or line.startswith("\t") or line.strip().startswith("-"):
                    continue
                skip_files_block = False
            if line.strip() == "---" and len(out) > 0:
                in_fm = False
        s = line.strip()
        if s.startswith("![["):
            continue
        if sub and f"[[{sub}/" in line:
            low = line.lower()
            if any(ext in low for ext in media_ext):
                continue
        out.append(line)
    return "\n".join(out)


def _extract_media_from_notes(
    note_texts: dict[str, str],  # rel_path -> raw text
    vault_path: Path,
) -> list[tuple[str, str]]:
    """English docstring omitted (see domain_messages.yaml)."""
    result: list[tuple[str, str]] = []
    seen: set[str] = set()

    for rel, raw in note_texts.items():
        if not raw.startswith("---"):
            continue
        parts = raw.split("---", 2)
        if len(parts) < 3:
            continue
        try:
            fm = yaml.safe_load(parts[1]) or {}
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        title = str(fm.get("title") or rel)
        att = fm.get("attachments") or {}
        files = att.get("files") or [] if isinstance(att, dict) else []
        if not isinstance(files, list):
            continue
        for f in files:
            if not isinstance(f, str) or f in seen:
                continue
            ext = Path(f).suffix.lower()
            if ext not in _MEDIA_EXTENSIONS:
                continue
            fp = (vault_path / f).resolve()
            try:
                fp.relative_to(vault_path.resolve())
            except ValueError:
                continue
            if fp.is_file():
                result.append((f, title))
                seen.add(f)
            if len(result) >= _max_media_per_query():
                return result
    return result


def _update_hit_stats(paths: list[str]) -> None:
    """English docstring omitted (see domain_messages.yaml)."""
    stats_file = Path(__file__).resolve().parent.parent.parent / "data" / "note_hit_stats.json"
    try:
        stats: dict[str, int] = json.loads(stats_file.read_text(encoding="utf-8")) if stats_file.exists() else {}
    except Exception:
        stats = {}
    for p in paths:
        stats[p] = stats.get(p, 0) + 1
    try:
        stats_file.parent.mkdir(parents=True, exist_ok=True)
        stats_file.write_text(json.dumps(stats, ensure_ascii=False, indent=0), encoding="utf-8")
    except Exception:
        log.warning("failed to write hit stats", exc_info=True)


def run_brain_query(
    vault_path: Path,
    agent_config_path: Path,
    llm: LLMClient,
    user_id: int,
    question: str,
) -> BrainQueryResult:
    """Module helper (user strings in YAML)."""
    def _err(msg: str) -> BrainQueryResult:
        return BrainQueryResult(text=msg)

    from knowledge_bot.i18n.domain_text import brain

    if not question.strip():
        return _err(brain("empty_question"))

    build_or_refresh_index(vault_path, force=False)
    idx = load_index()
    entries = idx.get("entries") or []
    if not entries:
        from shared.vault_layout import knowledge_subdir

        return _err(brain("empty_index", subdir=knowledge_subdir()))

    valid = {e["rel_path"] for e in entries if isinstance(e.get("rel_path"), str)}
    entries_by_path = {e["rel_path"]: e for e in entries if isinstance(e.get("rel_path"), str)}

    hist = load_history(user_id, max_turns=8)
    hist_block = format_history_for_prompt(hist)

    compact_catalog, short_to_full = _build_compact_catalog(entries)
    preselect_sys = load_prompt(agent_config_path, "query_preselect")
    preselect_user = (
        brain("prompt_question", question=question)
        + brain("prompt_history", history=hist_block or brain("history_none"))
        + brain("prompt_all_notes", catalog=compact_catalog)
    )
    try:
        pre_raw = llm.chat_json(
            preselect_sys,
            preselect_user,
            timeout=_preselect_timeout(),
            max_tokens=_preselect_max_tokens(),
        ).content
    except Exception:
        log.exception("preselect step failed")
        pre_raw = {}
    if _llm_json_failed(pre_raw):
        log.error("preselect: truncated/invalid JSON from LLM (see shared.llm finish_reason)")
        pre_raw = {}
    elif isinstance(pre_raw, dict) and pre_raw.get("_salvaged"):
        log.warning("preselect: salvaged response from truncated JSON")

    llm_paths = _parse_preselect(pre_raw if isinstance(pre_raw, dict) else {}, short_to_full)
    if not llm_paths and isinstance(pre_raw, dict) and pre_raw:
        log.warning(
            "preselect LLM returned 0 parsed paths; keys=%s",
            sorted(pre_raw.keys()),
        )
    candidate_paths = llm_paths
    if not candidate_paths:
        return _err(brain("preselect_none", count=len(entries)))

    candidates = [entries_by_path[p] for p in candidate_paths if p in entries_by_path]
    cap = _select_candidates_max()
    if len(candidates) > cap:
        log.info(
            "preselect: cap candidates %d → %d for select step",
            len(candidates),
            cap,
        )
        candidates = candidates[:cap]
    log.info("preselect: %d candidates → select step", len(candidates))

    summary_catalog = _build_summary_catalog(candidates)
    select_sys = load_prompt(agent_config_path, "query_select")
    select_user = (
        brain("prompt_question", question=question)
        + brain("prompt_history", history=hist_block or brain("history_none"))
        + brain("prompt_candidates", catalog=summary_catalog)
    )
    try:
        sel_raw = llm.chat_json(
            select_sys,
            select_user,
            timeout=_select_timeout(),
            max_tokens=_select_max_tokens(),
        ).content
    except Exception:
        log.exception("select step failed")
        sel_raw = {}
    if _llm_json_failed(sel_raw):
        log.error("select: truncated/invalid JSON from LLM")
        return _err(brain("select_truncated_json"))

    if not isinstance(sel_raw, dict):
        sel_raw = {}

    final_paths = _normalize_select_result(sel_raw.get("paths"), valid)
    if not final_paths:
        reason = (sel_raw.get("reason") or "").strip()
        if candidate_paths:
            cap_final = _max_selected_paths()
            final_paths = candidate_paths[:cap_final]
            log.warning(
                "select LLM returned 0 paths (%s); using top %d preselect candidates",
                reason or "no reason",
                len(final_paths),
            )
        else:
            return _err(
                brain("no_matching_notes", reason_suffix=(f" {reason}" if reason else ""))
            )

    raw_note_texts: dict[str, str] = {}  # rel_path -> raw text (for media extraction)
    full_notes: list[str] = []
    for rel in final_paths:
        sp = _safe_note_path(vault_path, rel)
        if not sp:
            log.warning("bad path from LLM: %s", rel)
            continue
        try:
            body = sp.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            log.warning("read failed %s: %s", sp, e)
            continue
        raw_note_texts[rel] = body
        clean_body = _strip_file_sections(body)
        full_notes.append(f"=== FILE: {rel} ===\n\n{clean_body}")

    if not full_notes:
        return _err(brain("notes_unreadable"))

    media_files = _extract_media_from_notes(raw_note_texts, vault_path)
    log.info("media_files for query: %d", len(media_files))

    answer_sys = load_prompt(agent_config_path, "query_answer")
    answer_user = (
        brain("prompt_question", question=question)
        + brain("prompt_history", history=hist_block or brain("history_none"))
        + brain("prompt_note_count", count=len(final_paths))
        + brain("prompt_full_texts")
        + "\n\n\n".join(full_notes)
    )
    try:
        ans = llm.chat(
            answer_sys,
            answer_user,
            timeout=_answer_timeout(),
            temperature=_answer_temperature(),
        ).content
    except Exception:
        log.exception("answer step failed")
        return _err(brain("answer_generation_error"))

    text = (ans if isinstance(ans, str) else str(ans)).strip()
    if not text:
        return _err(brain("empty_model_answer"))

    _update_hit_stats(final_paths)
    try:
        append_turn(user_id, question, text)
    except Exception:
        log.warning("failed to save history", exc_info=True)

    return BrainQueryResult(text=text, media_files=media_files)


from shared.telegram_utils import split_message as split_telegram_chunks
