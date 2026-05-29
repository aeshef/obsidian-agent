"""Ensure tags.txt includes DeepSeek JSON-mode instructions (word json in prompt)."""
from __future__ import annotations

import argparse
from pathlib import Path

from shared.domain_messages import dmsg


def _json_append() -> str:
    return dmsg("knowledge_tags_prompt", "json_append").strip()


def _tags_starter() -> str:
    starter = dmsg("knowledge_tags_prompt", "tags_starter").strip()
    return starter + "\n\n" + _json_append() + "\n"


def _example_is_stub(example_path: Path) -> bool:
    from shared.prompts import _is_comment_stub

    return _is_comment_stub(example_path.read_text(encoding="utf-8").strip())


def ensure_tags_prompt(tags_path: Path, example_path: Path) -> str:
    """Returns action: created | patched | ok."""
    if not example_path.is_file():
        raise FileNotFoundError(f"example not found: {example_path}")

    if not tags_path.is_file():
        tags_path.parent.mkdir(parents=True, exist_ok=True)
        if _example_is_stub(example_path):
            tags_path.write_text(_tags_starter(), encoding="utf-8")
        else:
            tags_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
        return "created"

    text = tags_path.read_text(encoding="utf-8")
    if "json" in text.lower():
        return "ok"

    tags_path.write_text(text.rstrip() + "\n\n" + _json_append() + "\n", encoding="utf-8")
    return "patched"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ensure knowledge_bot tags.txt has JSON output instructions")
    ap.add_argument(
        "--tags",
        type=Path,
        help="Path to tags.txt (default: knowledge_bot/config/prompts/tags.txt under monorepo root)",
    )
    ap.add_argument(
        "--example",
        type=Path,
        help="Path to tags.example.txt",
    )
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    kb = root / "knowledge_bot"
    tags = args.tags or (kb / "config" / "prompts" / "tags.txt")
    example = args.example or (kb / "config" / "prompts" / "tags.example.txt")

    action = ensure_tags_prompt(tags, example)
    print(f"{action}: {tags}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
