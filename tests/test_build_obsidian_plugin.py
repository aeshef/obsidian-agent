import shutil
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


_BUILDER_PATH = Path(__file__).resolve().parents[1] / "scripts/build_obsidian_plugin.py"
_BUILDER_SPEC = spec_from_file_location("build_obsidian_plugin", _BUILDER_PATH)
assert _BUILDER_SPEC is not None and _BUILDER_SPEC.loader is not None
build_obsidian_plugin = module_from_spec(_BUILDER_SPEC)
_BUILDER_SPEC.loader.exec_module(build_obsidian_plugin)


def _write_sources(ui_root: Path) -> None:
    for relative, content in {
        "vendor/echarts.js": "module.exports = 'charts';",
        "plugin-src/core.js": "module.exports = 'core';",
        "plugin-src/dashboard.js": "const dashboard = true;",
        "plugin-src/main.js": "const main = true;",
    }.items():
        path = ui_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_check_accepts_matching_bundle_without_writing(tmp_path: Path, capsys):
    ui_root = tmp_path / "obsidian_ui"
    _write_sources(ui_root)
    output = ui_root / "plugin/main.js"
    output.parent.mkdir(parents=True)
    output.write_text(build_obsidian_plugin.build_bundle(ui_root), encoding="utf-8")

    before = output.read_bytes()
    assert build_obsidian_plugin.check_bundle(ui_root) is True
    assert output.read_bytes() == before
    assert "up to date" in capsys.readouterr().out


def test_check_rejects_stale_bundle_without_writing(tmp_path: Path, capsys):
    ui_root = tmp_path / "obsidian_ui"
    _write_sources(ui_root)
    output = ui_root / "plugin/main.js"
    output.parent.mkdir(parents=True)
    output.write_text("old bundle", encoding="utf-8")

    assert build_obsidian_plugin.check_bundle(ui_root) is False
    assert output.read_text(encoding="utf-8") == "old bundle"
    assert "stale" in capsys.readouterr().out


def test_check_rejects_missing_bundle_without_creating_it(tmp_path: Path, capsys):
    ui_root = tmp_path / "obsidian_ui"
    _write_sources(ui_root)

    assert build_obsidian_plugin.check_bundle(ui_root) is False
    assert not (ui_root / "plugin/main.js").exists()
    assert "missing" in capsys.readouterr().out


def test_cli_check_uses_configured_root_and_returns_failure_for_stale_bundle(
    tmp_path: Path, monkeypatch, capsys
):
    ui_root = tmp_path / "obsidian_ui"
    _write_sources(ui_root)
    output = ui_root / "plugin/main.js"
    output.parent.mkdir(parents=True)
    output.write_text("old bundle", encoding="utf-8")
    monkeypatch.setattr(build_obsidian_plugin, "DEFAULT_UI_ROOT", ui_root)

    assert build_obsidian_plugin.main(["--check"]) == 1
    assert output.read_text(encoding="utf-8") == "old bundle"
    assert "stale" in capsys.readouterr().out


def test_importing_builder_does_not_write_bundle(tmp_path: Path):
    script = tmp_path / "scripts/build_obsidian_plugin.py"
    script.parent.mkdir(parents=True)
    shutil.copyfile(_BUILDER_PATH, script)
    ui_root = tmp_path / "shared/obsidian_ui"
    _write_sources(ui_root)
    output = ui_root / "plugin/main.js"
    output.parent.mkdir(parents=True)
    output.write_text("keep this generated file untouched", encoding="utf-8")

    subprocess.run(
        [sys.executable, "-c", "import runpy, sys; runpy.run_path(sys.argv[1])", str(script)],
        cwd=tmp_path,
        check=True,
    )
    assert output.read_text(encoding="utf-8") == "keep this generated file untouched"
