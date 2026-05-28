"""Load prompts and text configs."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("shared.prompts")


def _is_comment_stub(text: str) -> bool:
    """No substantive prompt body (only # / HTML comments / whitespace)."""
    substantive: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        if s.startswith("<!--") and "-->" in s:
            continue
        substantive.append(s)
    return not substantive


def _resolve_text_path(path: Path) -> Path | None:
    """First {name}.txt (prod/local), else {name}.example.txt (git template)."""
    if path.exists():
        return path
    if path.suffix == ".txt":
        example = path.with_name(f"{path.stem}.example.txt")
        if example.exists():
            return example
    return None


def load_prompt(
    config_dir: Path,
    name: str,
    *,
    required: bool = False,
    subdir: str = "prompts",
) -> str:
    # Prod: name.txt (not in git). Git: name.example.txt — fallback when .txt missing locally.
    path = config_dir / subdir / f"{name}.txt"
    resolved = _resolve_text_path(path)
    if resolved is None:
        if required:
            raise FileNotFoundError(f"Prompt not found: {path} (nor {path.stem}.example.txt)")
        return ""
    text = resolved.read_text(encoding="utf-8").strip()
    if resolved.name.endswith(".example.txt") and _is_comment_stub(text):
        log.error(
            "Prompt %s: only stub %s exists — create and fill %s (do not commit to git)",
            name,
            resolved.name,
            path.name,
        )
        return ""
    from shared.capabilities.prompt_filter import filter_prompt_capabilities
    from shared.capabilities.prompt_preamble import augment_prompt_capabilities

    filtered = filter_prompt_capabilities(text)
    return augment_prompt_capabilities(name, filtered)


def load_text(path: Path, *, default: str = "") -> str:
    resolved = _resolve_text_path(path)
    if resolved is None:
        return default
    try:
        return resolved.read_text(encoding="utf-8").strip()
    except Exception as e:
        log.error("Failed to read %s: %s", path, e, exc_info=True)
        return default
