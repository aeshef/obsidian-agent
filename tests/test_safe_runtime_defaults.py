from __future__ import annotations

import subprocess
import shlex
from pathlib import Path


def test_capabilities_shell_fails_closed_without_exporter(tmp_path: Path):
    script = Path(__file__).resolve().parent.parent / "scripts/lib/capabilities.sh"
    root = tmp_path / "agent"
    root.mkdir()

    probe = (
        f"AGENT_ROOT={shlex.quote(str(root))} source {shlex.quote(str(script))}; "
        "cap_load_env >/dev/null 2>&1 || true; "
        "cap_step_enabled SYNC_KB_MAINTENANCE; echo step=$?; "
        "cap_module_enabled KNOWLEDGE; echo module=$?"
    )
    result = subprocess.run(
        ["bash", "-lc", probe],
        text=True,
        capture_output=True,
        check=True,
    )

    assert "step=1" in result.stdout
    assert "module=1" in result.stdout


def test_vault_maintenance_example_is_safe(monkeypatch, tmp_path: Path):
    from knowledge_bot.services.vault_maintenance import runner

    kb_root = tmp_path / "knowledge_bot"
    config_dir = kb_root / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "vault_maintenance.yaml.example").write_text(
        "\n".join(
            [
                "daily:",
                "  enabled: false",
                "apply_wikilinks:",
                "  enabled: true",
                "  apply: false",
                "apply_duplicates:",
                "  enabled: true",
                "  apply: false",
                "  max_delete_per_run: 0",
                "export_orphans:",
                "  cleanup:",
                "    enabled: false",
                "    delete_cap: 0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "_kb_root", lambda: kb_root)

    cfg = runner.load_maintenance_config(tmp_path / "missing")

    assert cfg["daily"]["enabled"] is False
    assert cfg["apply_wikilinks"]["apply"] is False
    assert cfg["apply_duplicates"]["apply"] is False
    assert cfg["export_orphans"]["cleanup"]["enabled"] is False
    assert cfg["export_orphans"]["cleanup"]["delete_cap"] == 0
