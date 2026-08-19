from __future__ import annotations

import re
import yaml
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from knowledge_bot.core.config import load_config
from knowledge_bot.core.settings import load_types_config
from knowledge_bot.i18n.domain_text import llm_default_type, render as render_msg
from shared.yaml_config import load_merged_config

_CONTACT_CFG_DIR = Path(__file__).resolve().parent.parent / "config"


@lru_cache(maxsize=1)
def _contact_handles_cfg() -> dict:
    return load_merged_config(str(_CONTACT_CFG_DIR), "contact_handles")


def _normalize_handle_key(raw_key: str) -> str | None:
    key = (raw_key or "").strip().lower()
    aliases = (_contact_handles_cfg().get("aliases") or {})
    for canonical, variants in aliases.items():
        if not isinstance(variants, list):
            continue
        if key == canonical.lower() or key in {str(v).lower() for v in variants}:
            return canonical
    return None


def _frontmatter_quoted_representer(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    """English docstring omitted (see domain_messages.yaml)."""
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')


def _strip_empty_md_sections(text: str) -> str:
    """English docstring omitted (see domain_messages.yaml)."""
    import re
    if not text or not text.strip():
        return ""
    parts = re.split(r"\n(?=## )", text)
    result = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.split("\n")
        if len(lines) <= 1:
            continue
        content = "\n".join(lines[1:]).strip()
        if not content:
            continue
        content_lines = [ln.strip() for ln in content.split("\n") if ln.strip()]
        if all(ln in ("-", "- ", "•", "• ") or re.match(r"^[-•]\s*$", ln) for ln in content_lines):
            continue
        result.append(part)
    return "\n\n".join(result) if result else ""


class _FrontmatterSafeDumper(yaml.SafeDumper):
    pass


_FrontmatterSafeDumper.add_representer(str, _frontmatter_quoted_representer)


def _reserialize_frontmatter_safe(content: str) -> str:
    """English docstring omitted (see domain_messages.yaml)."""
    m = re.match(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", content, re.DOTALL)
    if not m:
        return content
    fm_raw = m.group(2)
    body = m.group(4)
    try:
        fm = yaml.safe_load(fm_raw)
    except yaml.YAMLError:
        return content
    if not isinstance(fm, dict):
        return content
    if fm.get("tags") is None:
        fm["tags"] = []
    from knowledge_bot.services.frontmatter_attachments import flatten_attachment_fields
    from knowledge_bot.services.tag_remap import (
        TAXONOMY_ASCII_MAP,
        canonicalize_tags,
        flatten_mapping,
        remap_category_field,
    )

    fm = flatten_attachment_fields(fm)
    final_map = flatten_mapping(TAXONOMY_ASCII_MAP)
    remap_category_field(fm, final_map)
    raw_tags = fm.get("tags")
    if isinstance(raw_tags, list) and raw_tags:
        fm["tags"] = canonicalize_tags([str(t) for t in raw_tags if t])
    try:
        fm_str = yaml.dump(
            fm,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            Dumper=_FrontmatterSafeDumper,
        ).strip()
    except Exception:
        return content
    return f"---\n{fm_str}\n---\n{body}"


def _yaml_safe(val: Any) -> str:
    """English docstring omitted (see domain_messages.yaml)."""
    if val is None:
        return ""
    s = str(val).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    return s.strip()


def _sanitize_payload(obj: Any) -> Any:
    """English docstring omitted (see domain_messages.yaml)."""
    if obj is None:
        return None
    if isinstance(obj, str):
        return _yaml_safe(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_payload(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_payload(x) for x in obj]
    return obj


def render_note(templates_dir: Path, payload: dict[str, Any]) -> str:
    derived = payload.get("_derived_for_render") or payload.get("derived") or {}
    raw_yt = (derived.get("yt_transcript_summary") or "") or (payload.get("yt_transcript_summary") or "")
    raw_yt = raw_yt.strip() if isinstance(raw_yt, str) else str(raw_yt or "").strip()
    raw_asr = (derived.get("asr_summary") or "") or (payload.get("asr_summary") or "")
    raw_asr = raw_asr.strip() if isinstance(raw_asr, str) else str(raw_asr or "").strip()

    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=select_autoescape([]))
    env.filters["yaml_safe"] = lambda x: _yaml_safe(x) if x is not None else ""
    payload = _sanitize_payload(payload) or {}
    type_name = payload.get("type") or llm_default_type()
    cfg = load_config()
    types_cfg = load_types_config(cfg.agent_config_path)
    template_name = types_cfg.template_for(type_name)
    template = env.get_template(template_name)
    data = {**payload}
    data.setdefault("created", date.today().isoformat())
    data.setdefault("raw_dir", payload.get("raw_dir", ""))
    # Provide safe defaults for nested structures expected by templates
    contact_type = str(
        _contact_handles_cfg().get("contact_type") or render_msg("default_contact_type")
    )
    if data.get("type") == contact_type:
        handles_raw = data.get("handles")
        # Normalize handles to dict: handle cases where LLM returns list or string
        if isinstance(handles_raw, dict):
            handles = handles_raw
        elif isinstance(handles_raw, list):
            # Convert list to dict: assume list of strings or dicts
            handles = {}
            for item in handles_raw:
                if isinstance(item, dict):
                    handles.update(item)
                elif isinstance(item, str):
                    # Try to parse string as key-value or use as value
                    if ":" in item or "=" in item:
                        parts = item.replace("=", ":").split(":", 1)
                        if len(parts) == 2:
                            key = parts[0].strip().lower()
                            val = parts[1].strip()
                            canon = _normalize_handle_key(key)
                            if canon:
                                handles[canon] = val
        elif isinstance(handles_raw, str):
            # Try to parse string representation
            handles = {}
            if handles_raw.strip():
                # Simple heuristic: if contains @, it's email; if starts with + or digits, it's phone
                if "@" in handles_raw:
                    handles["email"] = handles_raw.strip()
                elif handles_raw.strip().startswith("+") or handles_raw.strip().replace("-", "").replace(" ", "").isdigit():
                    handles["phone"] = handles_raw.strip()
                else:
                    # Assume it's telegram handle
                    handles["tg"] = handles_raw.strip()
        else:
            handles = {}
        handles.setdefault("tg", "")
        handles.setdefault("email", "")
        handles.setdefault("phone", "")
        data["handles"] = handles
    content = template.render(**data)
    # Optional images section (embed) and files section (links)
    att = data.get("attachments") or {}
    files = [p for p in (att.get("files") or []) if isinstance(p, str) and p.strip()]
    if files:
        image_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
        import os
        imgs = [p for p in files if os.path.splitext(p)[1].lower() in image_exts]
        docs = [p for p in files if p not in imgs]
        if imgs:
            lines_i = [render_msg("section_images")]
            for p in imgs:
                lines_i.append(f"![[{p}]]\n")
            content = f"{content}\n{''.join(lines_i)}"
        if docs:
            lines_f = [render_msg("section_files")]
            for p in docs:
                name = p.split("/")[-1]
                lines_f.append(f"- [[{p}|{name}]]\n")
            content = f"{content}\n{''.join(lines_f)}"
    # Optional links section with anchors and plain links fallback
    links_anchors = data.get("links_anchors") or []
    extra_links = []
    for u in (att.get("links") or []):
        if isinstance(u, str) and u.strip():
            extra_links.append(u)
    if isinstance(links_anchors, list) and (links_anchors or extra_links):
        lines = [render_msg("section_links")]
        seen = set()
        for item in links_anchors:
            url = (item.get("url") if isinstance(item, dict) else None) or ""
            text = (item.get("text") if isinstance(item, dict) else None) or url
            if text and url and url not in seen:
                lines.append(f"- [{text}]({url})\n")
                seen.add(url)
        for url in extra_links:
            if url not in seen:
                lines.append(f"- {url}\n")
                seen.add(url)
        if len(lines) > 1:
            content = f"{content}\n{''.join(lines)}"
    raw_text = (data.get("raw_text") or "").strip()
    if raw_text:
        content = f"{content}{render_msg('section_raw_text', raw_text=raw_text)}"
    asr_summary = _strip_empty_md_sections(raw_asr)
    if asr_summary:
        content = f"{content}{render_msg('section_asr_summary', asr_summary=asr_summary)}"
    yt_summary = _strip_empty_md_sections(raw_yt) if ("## " in raw_yt) else (raw_yt.strip() if raw_yt else "")
    if yt_summary and data.get("type") != render_msg("note_type_video"):
        body_yt = yt_summary.strip()
        for lead in (render_msg("lead_yt_summary"), render_msg("lead_key_theses")):
            if body_yt.lower().startswith(lead):
                rest = body_yt.split("\n", 1)
                body_yt = rest[1].strip() if len(rest) > 1 else ""
                break
        if body_yt:
            content = f"{content}{render_msg('section_yt_summary', body_yt=body_yt)}"
    asr_text = (data.get("asr_text") or "").strip()
    if asr_text:
        content = f"{content}{render_msg('section_transcript', asr_text=asr_text)}"
    vision_text = (data.get("vision_text") or "").strip()
    if vision_text:
        content = f"{content}{render_msg('section_vision', vision_text=vision_text)}"
    if data.get("type") == render_msg("note_type_video") and yt_summary:
        body = yt_summary.strip()
        if body.lower().startswith(render_msg("lead_key_theses")):
            rest = body.split("\n", 1)
            body = rest[1].strip() if len(rest) > 1 else ""
        h = render_msg("heading_key_theses")
        next_h = render_msg("heading_insights")
        i = content.find(h)
        j = content.find(next_h, i) if i != -1 else -1
        if i != -1 and j != -1 and body:
            content = content[:i] + h + "\n\n" + body + "\n\n" + content[j:]
    # Remove placeholder line for raw_dir (redundant regardless of presence)
    lines = content.splitlines()
    prefix = render_msg("line_raw_files_prefix")
    lines = [ln for ln in lines if not ln.strip().startswith(prefix)]
    content = "\n".join(lines)
    content = _reserialize_frontmatter_safe(content)
    return content


