"""Vault audit report (tags section + report assembly)."""
from __future__ import annotations

from pathlib import Path

import pytest

from knowledge_bot.services.vault_audit.report import (
    _format_maintenance_run,
    build_vault_audit_report,
)
from knowledge_bot.services.vault_audit.tags import render_tags_report


def _write_note(root: Path, rel: str, *, tags: list[str] | None = None) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    tag_line = ""
    if tags is not None:
        tag_line = "tags:\n" + "\n".join(f"  - {t}" for t in tags) + "\n"
    path.write_text(
        f"---\n{tag_line}created: 2026-01-01\n---\n\n# Note\n",
        encoding="utf-8",
    )


@pytest.fixture
def mini_vault(tmp_path: Path) -> Path:
    kd = "700_База_Данных"
    _write_note(tmp_path, f"{kd}/Alpha.md", tags=["domain/test", "topic/foo"])
    _write_note(tmp_path, f"{kd}/Beta.md", tags=[])
    return tmp_path


def test_render_tags_report_lists_untagged(mini_vault: Path) -> None:
    text = render_tags_report(mini_vault)
    assert "700_База_Данных" in text
    assert "Beta.md" in text


def test_build_vault_audit_report_sections(mini_vault: Path) -> None:
    report = build_vault_audit_report(mini_vault)
    assert "## 1." in report or "## 1. Теги" in report
    assert "Beta.md" in report
    assert "## 3." in report or "обслуживание" in report.lower() or "maintenance" in report.lower()


def test_default_vault_audit_report_path_not_under_charts() -> None:
    from knowledge_bot.services.vault_audit.report import _default_report_rel

    rel = _default_report_rel()
    parts = rel.split("/")
    assert "Графики" not in parts and "Charts" not in parts
    assert rel.endswith(".md")


def test_format_maintenance_run_filters_macos_objc_noise(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LOCALE", "ru")
    run = {
        "ok": True,
        "steps": [
            {
                "name": "reprocess_notes",
                "returncode": 0,
                "seconds": 1.2,
                "stdout_tail": "ok\n",
                "stderr_tail": (
                    "objc[123]: Class AVFFrameReceiver is implemented in both "
                    "/cv2/libavdevice.dylib and /av/libavdevice.dylib. "
                    "This may cause spurious casting failures.\n"
                ),
            }
        ],
    }

    text = "\n".join(_format_maintenance_run(run))
    assert "objc[" not in text
    assert "AVFFrameReceiver" not in text
