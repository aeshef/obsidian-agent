"""Host composition-root import boundary (OSS audit F12).

Composition root: ``unified_bot/host`` (outside ``shared/``).
``shared/memory`` may still import bots. New bot imports elsewhere in
``shared/`` fail CI. Host shims under ``shared/telegram/host`` are removed.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"
ALLOWED_REL_DIRS = {
    Path("shared/memory"),
}
KNOWN_BOT_IMPORT_FILES = frozenset()
BOT_ROOTS = frozenset({"planning_bot", "finance_bot", "knowledge_bot", "bot"})


def _in_allowed_dir(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    return any(rel == zone or zone in rel.parents for zone in ALLOWED_REL_DIRS)


def _imports_bot(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in BOT_ROOTS:
                    hits.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root in BOT_ROOTS:
                hits.append(node.module)
    return hits


def test_shared_bot_imports_only_in_documented_zones():
    unexpected: list[str] = []
    for path in SHARED.rglob("*.py"):
        if _in_allowed_dir(path):
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        hits = _imports_bot(tree)
        if not hits:
            continue
        if rel in KNOWN_BOT_IMPORT_FILES:
            continue
        unexpected.append(f"{rel}: {hits}")
    assert not unexpected, "new bot imports outside composition allowlist:\n" + "\n".join(
        unexpected
    )


def test_unified_bot_host_is_composition_root():
    host = ROOT / "unified_bot" / "host" / "bootstrap.py"
    assert host.is_file()
    shim_py = list((ROOT / "shared" / "telegram" / "host").glob("*.py"))
    assert not shim_py, f"host shims must be deleted, found: {shim_py}"
