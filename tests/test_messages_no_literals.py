"""Ban user-facing Cyrillic literals in Telegram reply calls (allowlist exceptions).

Policy: user-visible strings belong in messages.ru.yaml / domain_messages.yaml.
Cyrillic detector uses Unicode range U+0400-U+04FF via chr() (no Cyrillic in this file).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ("shared/telegram", "finance_bot/bot", "planning_bot/app", "knowledge_bot/app")
ALLOW_FILES = {
    ROOT / "shared/telegram/host/wire.py",
}
_CYRILLIC = re.compile(f"[{chr(0x400)}-{chr(0x4FF)}]")
_REPLY_METHODS = frozenset({
    "answer",
    "reply",
    "reply_text",
    "edit_text",
    "edit_message_text",
    "send_message",
})
_TEXT_KWARGS = frozenset({"text", "caption"})


def _string_has_cyrillic(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return bool(_CYRILLIC.search(node.value))
    if isinstance(node, ast.JoinedStr):
        return any(
            isinstance(v, ast.Constant) and isinstance(v.value, str) and _CYRILLIC.search(v.value)
            for v in node.values
        )
    return False


def _iter_handler_files() -> list[Path]:
    out: list[Path] = []
    for sub in SCAN_DIRS:
        base = ROOT / sub
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if path in ALLOW_FILES:
                continue
            out.append(path)
    return sorted(out)


def test_no_cyrillic_literals_in_reply_calls() -> None:
    offenders: list[str] = []
    for path in _iter_handler_files():
        rel = path.relative_to(ROOT)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as e:
            offenders.append(f"{rel}: syntax error: {e}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = None
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            if name not in _REPLY_METHODS:
                continue
            for kw in node.keywords:
                if kw.arg in _TEXT_KWARGS and _string_has_cyrillic(kw.value):
                    offenders.append(f"{rel}:{kw.lineno}: reply kw {kw.arg}")
            if node.args and _string_has_cyrillic(node.args[0]):
                offenders.append(f"{rel}:{node.args[0].lineno}: reply arg0")
    assert not offenders, "Cyrillic in reply calls:\n" + "\n".join(offenders[:40])
