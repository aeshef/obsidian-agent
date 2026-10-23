"""The plugin builder can detect stale output without changing it."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_obsidian_plugin.py"


def _builder():
    spec = importlib.util.spec_from_file_location("build_obsidian_plugin", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sources(root: Path) -> None:
    for relative, content in {
        "vendor/echarts.js": "vendor code",
        "plugin-src/core.js": "core code",
        "plugin-src/dashboard.js": "dashboard code",
        "plugin-src/main.js": "main code",
    }.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    (root / "plugin").mkdir()


def test_import_does_not_write_bundle(tmp_path: Path) -> None:
    _sources(tmp_path)
    builder = _builder()
    assert not (tmp_path / "plugin" / "main.js").exists()
    assert "const echarts=" in builder.build_bundle(tmp_path)
    assert not (tmp_path / "plugin" / "main.js").exists()


def test_check_matching_bundle_is_read_only(tmp_path: Path, capsys) -> None:
    _sources(tmp_path)
    builder = _builder()
    output = tmp_path / "plugin" / "main.js"
    assert builder.main([], root=tmp_path) == 0
    expected = output.read_bytes()
    assert builder.main(["--check"], root=tmp_path) == 0
    assert output.read_bytes() == expected
    assert "up to date" in capsys.readouterr().out


def test_check_stale_bundle_is_read_only(tmp_path: Path, capsys) -> None:
    _sources(tmp_path)
    builder = _builder()
    output = tmp_path / "plugin" / "main.js"
    output.write_text("old bundle")
    assert builder.main(["--check"], root=tmp_path) == 1
    assert output.read_text() == "old bundle"
    assert "Stale" in capsys.readouterr().out


def test_check_missing_bundle_is_read_only(tmp_path: Path, capsys) -> None:
    _sources(tmp_path)
    builder = _builder()
    output = tmp_path / "plugin" / "main.js"
    assert builder.main(["--check"], root=tmp_path) == 1
    assert not output.exists()
    assert "Missing" in capsys.readouterr().out
