"""Bundle local chart code for desktop and mobile (no Node APIs at runtime)."""

from __future__ import annotations

import argparse
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "shared" / "obsidian_ui"


def module(path: Path) -> str:
    return (
        "(function(){const module={exports:{}};const exports=module.exports;\n"
        + path.read_text(encoding="utf-8")
        + "\nreturn module.exports;})()"
    )


def build_bundle(root: Path = PLUGIN_ROOT) -> str:
    """Return the complete bundle without writing generated files."""
    return "\n".join(
        [
            "const echarts=" + module(root / "vendor" / "echarts.js") + ";",
            "const chartCore=" + module(root / "plugin-src" / "core.js") + ";",
            (root / "plugin-src" / "dashboard.js").read_text(encoding="utf-8"),
            (root / "plugin-src" / "main.js").read_text(encoding="utf-8"),
        ]
    )


def main(argv: list[str] | None = None, *, root: Path = PLUGIN_ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check that the generated bundle is current without writing it")
    args = parser.parse_args(argv)

    output = root / "plugin" / "main.js"
    bundle = build_bundle(root).encode("utf-8")
    if args.check:
        if not output.is_file():
            print(f"Missing generated bundle: {output}. Run this script without --check to build it.")
            return 1
        if output.read_text(encoding="utf-8") != bundle.decode("utf-8"):
            print(f"Stale generated bundle: {output}. Run this script without --check to rebuild it.")
            return 1
        print(f"Generated bundle is up to date: {output}")
        return 0

    output.write_bytes(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
