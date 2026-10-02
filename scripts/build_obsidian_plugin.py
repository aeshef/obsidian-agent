"""Bundle local chart code for desktop and mobile (no Node APIs at runtime)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence


DEFAULT_UI_ROOT = Path(__file__).resolve().parents[1] / "shared/obsidian_ui"


def _module(path: Path) -> str:
    return (
        "(function(){const module={exports:{}};const exports=module.exports;\n"
        + path.read_text(encoding="utf-8")
        + "\nreturn module.exports;})()"
    )


def build_bundle(ui_root: Path = DEFAULT_UI_ROOT) -> str:
    """Return the deterministic plugin bundle for a UI source directory."""
    parts = [
        "const echarts=" + _module(ui_root / "vendor/echarts.js") + ";",
        "const chartCore=" + _module(ui_root / "plugin-src/core.js") + ";",
        (ui_root / "plugin-src/dashboard.js").read_text(encoding="utf-8"),
        (ui_root / "plugin-src/main.js").read_text(encoding="utf-8"),
    ]
    return "\n".join(parts)


def write_bundle(ui_root: Path = DEFAULT_UI_ROOT) -> Path:
    """Build and write the generated plugin bundle, preserving default CLI behavior."""
    output_path = ui_root / "plugin/main.js"
    output_path.write_text(build_bundle(ui_root), encoding="utf-8")
    return output_path


def check_bundle(ui_root: Path = DEFAULT_UI_ROOT) -> bool:
    """Return whether the checked-in bundle matches its sources, without writing."""
    output_path = ui_root / "plugin/main.js"
    if not output_path.is_file():
        print(f"Plugin bundle is missing: {output_path}")
        return False

    expected = build_bundle(ui_root)
    actual = output_path.read_text(encoding="utf-8")
    if actual != expected:
        print(
            f"Plugin bundle is stale: {output_path}; "
            "run python scripts/build_obsidian_plugin.py"
        )
        return False

    print(f"Plugin bundle is up to date: {output_path}")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the generated plugin bundle is missing or out of date (read-only)",
    )
    args = parser.parse_args(argv)

    if args.check:
        return 0 if check_bundle(DEFAULT_UI_ROOT) else 1
    write_bundle(DEFAULT_UI_ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
