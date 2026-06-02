#!/usr/bin/env python3
"""Fix build/maintenance scripts: vault_paths_config + _vault (no Cyrillic paths in .py)."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "planning_bot" / "scripts"

CHART_FILES: dict[str, tuple[str, str]] = {
    "build_deadline_horizon_chart.py": ("chart_deadline_horizon_png", "chart_deadline_horizon_md"),
    "build_daily_task_activity_chart.py": ("chart_daily_activity_png", "chart_daily_activity_md"),
    "build_daily_completions_by_category_chart.py": (
        "chart_completions_by_category_png",
        "chart_completions_by_category_md",
    ),
    "build_open_pipeline_by_category_chart.py": (
        "chart_open_pipeline_png",
        "chart_open_pipeline_md",
    ),
    "build_iphone_nutrition_chart.py": ("chart_nutrition_png", "chart_nutrition_md"),
}

VAULT_PDMSG_KEYS = (
    "auto_0785c86cb9",
    "auto_1c7277d3a5",
    "auto_1f4101e6f4",
    "auto_a7c14af2a8",
    "auto_73f5ba424f",
    "auto_8c60238010",
    "auto_402d37af44",
    "auto_704cc97621",
)

IMPORT_VAULT = "from planning_bot.scripts._vault import discover_vault, vault_layout\n"
IMPORT_VAULT_FILE = "from shared.vault_paths_config import vault_file\n"


def _strip_discover_vault(src: str) -> str:
    src = re.sub(
        r"\ndef _discover_vault\(start: Path\) -> Path:\n(?:    .+\n)+?    return .+\n",
        "",
        src,
    )
    src = re.sub(
        r"\ndef _paths\(vault: Path, out_dir: Path \| None\) -> Path:\n(?:    .+\n)+?    return out\n",
        "",
        src,
    )
    src = src.replace("_discover_vault(", "discover_vault(")
    return src


def _ensure_imports(src: str, need_vault_file: bool) -> str:
    if "from planning_bot.scripts._vault import" not in src:
        anchor = "from planning_bot.core.pdmsg import pdmsg"
        if anchor in src:
            src = src.replace(anchor, anchor + "\n" + IMPORT_VAULT.rstrip(), 1)
        elif "from __future__" in src:
            src = src.replace(
                "from __future__ import annotations\n\n",
                "from __future__ import annotations\n\n" + IMPORT_VAULT,
                1,
            )
    if need_vault_file and "from shared.vault_paths_config import vault_file" not in src:
        src = src.replace(
            "from planning_bot.scripts._vault import discover_vault, vault_layout",
            "from planning_bot.scripts._vault import discover_vault, vault_layout\n"
            + IMPORT_VAULT_FILE.rstrip(),
            1,
        )
    return src


def _fix_chart_names(src: str, png_key: str, md_key: str) -> str:
    src = re.sub(
        r"PNG_NAME\s*=\s*pdmsg\([^)]+\)",
        f'PNG_NAME = vault_file("{png_key}")',
        src,
    )
    src = re.sub(
        r"MD_NAME\s*=\s*pdmsg\([^)]+\)",
        f'MD_NAME = vault_file("{md_key}")',
        src,
    )
    # pdmsg vault folder paths -> vault_layout
    src = re.sub(
        r"vault / pdmsg\(\"auto_1c7277d3a5\"\) / pdmsg\(\"auto_1f4101e6f4\"\)",
        "vault_layout(vault)[\"charts\"]",
        src,
    )
    src = re.sub(
        r"\(p / pdmsg\(\"auto_0785c86cb9\"\)\)\.(?:is_dir|exists)\(\)",
        '(p / vault_layout(p)["tasks"].relative_to(p)).exists()',
        src,
    )
    # simpler: replace discover markers
    src = src.replace('pdmsg("auto_0785c86cb9")', 'folder("tasks")')
    src = src.replace('pdmsg("auto_1c7277d3a5")', 'folder("dashboards")')
    src = src.replace('pdmsg("auto_1f4101e6f4")', 'dashboards_sub("charts")')
    if 'folder("tasks")' in src and "from shared.vault_paths_config import" not in src:
        src = src.replace(
            "from shared.vault_paths_config import vault_file",
            "from shared.vault_paths_config import dashboards_sub, folder, vault_file",
            1,
        )
        if "from shared.vault_paths_config import" not in src:
            anchor = "from planning_bot.scripts._vault import"
            if anchor in src:
                idx = src.find(anchor)
                line_end = src.find("\n", idx)
                src = (
                    src[: line_end + 1]
                    + "from shared.vault_paths_config import dashboards_sub, folder\n"
                    + src[line_end + 1 :]
                )
    return src


def _english_docstring(src: str, name: str) -> str:
    title = name.replace("build_", "").replace("_", " ").removesuffix(".py")
    return re.sub(
        r'"""Maintenance script for planning bot vault data\."""',
        f'"""Build {title} from vault data."""',
        src,
        count=1,
    )


def patch_file(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    orig = src
    src = _strip_discover_vault(src)
    src = _english_docstring(src, path.name)
    keys = CHART_FILES.get(path.name)
    if keys:
        src = _fix_chart_names(src, keys[0], keys[1])
        src = _ensure_imports(src, need_vault_file=True)
    else:
        src = _ensure_imports(src, need_vault_file=False)
    if src != orig:
        path.write_text(src, encoding="utf-8")
        return True
    return False


def main() -> None:
    n = 0
    for p in sorted(SCRIPTS.glob("*.py")):
        if p.name.startswith("_") or p.name.startswith("migrate") or p.name.startswith("zero"):
            continue
        if p.name in {"patch_scripts_no_cyrillic.py", "fix_agent_tools.py", "strip_remaining_cyrillic.py"}:
            continue
        if patch_file(p):
            n += 1
            print("patched", p.name)
    print(f"done: {n} files")


if __name__ == "__main__":
    main()
