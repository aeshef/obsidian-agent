"""Inject [[wikilinks]] into note body (threshold + LLM keyword pick)."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from knowledge_bot.i18n.domain_text import wikilink_noise_tokens
from knowledge_bot.services.tags_inventory import load_tags_inventory

WIKILINKS_THRESHOLD = 10
WIKILINKS_NOISE = wikilink_noise_tokens()
_FRONTMATTER_SPLIT = re.compile(r"^(---\s*\n.*?\n---\s*\n)(.*)$", re.DOTALL)


def split_frontmatter(content: str) -> tuple[str, str]:
    """Keep YAML (including tags) out of wikilink replacement."""
    m = _FRONTMATTER_SPLIT.match(content or "")
    if m:
        return m.group(1), m.group(2)
    return "", content or ""


def _extract_body(note_path: Path) -> str:
    try:
        text = note_path.read_text(encoding="utf-8", errors="ignore")
        m = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
        return text[m.end():] if m else text
    except Exception:
        return ""


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    cyr = f"{chr(0x430)}-{chr(0x45F)}{chr(0x451)}"
    pat = rf"[a-z{cyr}0-9]+(?:[-_][a-z{cyr}0-9]+)*"
    tokens = re.findall(pat, text)
    return [t for t in tokens if len(t) >= 2]


def get_candidates(vault_path: Path, agent_config_path: Path, threshold: int = WIKILINKS_THRESHOLD) -> dict[str, str]:
    """Topic/domain candidates with in_text >= threshold."""
    from shared.vault_layout import knowledge_subdir

    inv = load_tags_inventory(agent_config_path)
    tags_dict = inv.get("tags", {})
    db_root = vault_path / knowledge_subdir()
    if not db_root.exists():
        return _candidates_from_tags_only(tags_dict)

    body_freq: Counter[str] = Counter()
    for np in db_root.rglob("*.md"):
        if "Export" in str(np):
            continue
        body_freq.update(_tokenize(_extract_body(np)))

    from knowledge_bot.services.tag_normalize import is_malformed_tag

    result = {}
    for tag, info in tags_dict.items():
        if is_malformed_tag(tag) or "/" not in tag:
            continue
        ns, value = tag.split("/", 1)
        if ns not in ("topic", "domain"):
            continue
        if value.strip().lower() in WIKILINKS_NOISE:
            continue
        examples = info.get("examples") or []
        if not examples:
            continue
        keyword = value.strip()
        if len(keyword) < 2:
            continue
        in_text = body_freq.get(keyword, 0) + body_freq.get(keyword.replace("-", "_"), 0)
        in_tags = info.get("count", 0)
        if in_text < threshold and in_tags < 2:
            continue
        link = str(examples[0]).replace("\\", "/").rstrip(".md")
        result[keyword] = link
    return result


def _candidates_from_tags_only(tags_dict: dict) -> dict[str, str]:
    """Helper."""
    result = {}
    for tag, info in tags_dict.items():
        if "/" not in tag or is_malformed_tag(tag) or info.get("count", 0) < 2:
            continue
        ns, value = tag.split("/", 1)
        if ns not in ("topic", "domain") or value.strip().lower() in WIKILINKS_NOISE:
            continue
        examples = info.get("examples") or []
        if not examples:
            continue
        result[value.strip()] = str(examples[0]).replace("\\", "/").rstrip(".md")
    return result


def _apply_wikilinks(content: str, keyword_to_link: dict[str, str], only_keywords: set[str] | None = None) -> str:
    """Replace keywords in the note body only — never in YAML frontmatter/tags."""
    prefix, body = split_frontmatter(content)
    work = body if prefix else content
    if not work or not keyword_to_link:
        return content
    if only_keywords is not None:
        keyword_to_link = {k: v for k, v in keyword_to_link.items() if k in only_keywords}
    if not keyword_to_link:
        return content
    items = sorted(keyword_to_link.items(), key=lambda x: -len(x[0]))

    def replace_in_text(text: str) -> str:
        for kw, link in items:
            pat = r"\b" + re.escape(kw) + r"\b"
            text = re.sub(pat, f"[[{link}]]", text)
        return text

    parts = re.split(r"(\[\[[^\]]*\]\]|```[\s\S]*?```)", work)
    result = []
    for part in parts:
        if part.startswith("[[") and part.endswith("]]") or part.startswith("```"):
            result.append(part)
        else:
            result.append(replace_in_text(part))
    return prefix + "".join(result)


def body_has_any_candidate(body: str, candidates: dict[str, str]) -> bool:
    """Helper."""
    if not body or not candidates:
        return False
    body_lower = body.lower()
    for kw in candidates:
        if len(kw) < 2:
            continue
        kw_lo = kw.lower()
        if len(kw_lo) <= 3:
            if re.search(r"\b" + re.escape(kw_lo) + r"\b", body_lower):
                return True
        else:
            if kw_lo in body_lower or kw_lo.replace("-", "_") in body_lower:
                return True
    return False


def inject_wikilinks(
    content: str,
    agent_config_path: Path,
    vault_path: Path | None = None,
    llm_client: "Any" | None = None,
) -> str:
    """Inject wikilinks (LLM picks keywords when client provided)."""
    vault = vault_path or agent_config_path.parent.parent
    candidates = get_candidates(vault, agent_config_path, threshold=WIKILINKS_THRESHOLD)
    prefix, body = split_frontmatter(content)
    work = body if prefix else content
    if not candidates:
        return content
    if len(work.strip()) < 50:
        return content
    if llm_client:
        if not body_has_any_candidate(work, candidates):
            return content
        new_body = inject_wikilinks_llm(work, candidates, llm_client, agent_config_path)
        return prefix + new_body
    return prefix + _apply_wikilinks(work, candidates, only_keywords=None)


def inject_wikilinks_llm(
    content: str,
    candidates: dict[str, str],
    llm_client: "Any",
    agent_config_path: Path,
) -> str:
    """LLM selects which candidate keywords become wikilinks in content."""
    if not content or not content.strip() or not candidates:
        return content
    try:
        from knowledge_bot.core.settings import load_prompt
        prompt = load_prompt(agent_config_path, "wikilinks_select")
        user = json.dumps({"content": content[:8000], "candidates": dict(list(candidates.items())[:80])}, ensure_ascii=False)
        resp = llm_client.chat_json(prompt, user).content or {}
        selected = resp.get("keywords", []) if isinstance(resp, dict) else []
        if not selected:
            return content
        only = {str(k).strip() for k in selected if str(k).strip() in candidates}
        return _apply_wikilinks(content, candidates, only_keywords=only)
    except Exception:
        return content
