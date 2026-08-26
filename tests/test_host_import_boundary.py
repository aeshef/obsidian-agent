"""Host composition-root import boundary (OSS audit F12).

Preferred composition root: ``shared/telegram/host`` + ``shared/memory``.
Other ``shared/`` modules that still import bots are frozen below — new
bot imports outside this allowlist fail CI (shrink over time; do not grow).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"
ALLOWED_REL_DIRS = {
    Path("shared/telegram/host"),
    Path("shared/memory"),
}
# Frozen debt — do not add paths. Prefer moving call sites into host/domains.
KNOWN_BOT_IMPORT_FILES = frozenset(
    {
        "shared/routines_paths.py",
        "shared/kanban_paths.py",
        "shared/capabilities/registry.py",
        "shared/capabilities/vault_routines_scaffold.py",
        "shared/capabilities/onboarding_verify.py",
        "shared/finance/txn_query.py",
        "shared/finance/broker_portfolio_sync.py",
        "shared/finance/broker_providers.py",
        "shared/analytics/daily_panel.py",
    }
)
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


def test_known_bot_import_files_still_exist():
    missing = [p for p in sorted(KNOWN_BOT_IMPORT_FILES) if not (ROOT / p).is_file()]
    assert not missing, "allowlist paths removed — drop from KNOWN_BOT_IMPORT_FILES: " + str(
        missing
    )
