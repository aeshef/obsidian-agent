"""Validate bootstrap checklist is present and well-formed."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_bootstrap_checklist_contract():
    path = ROOT / "config" / "agent" / "bootstrap_checklist.yaml.example"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["id"] == "obsidian-agent-bootstrap"
    phases = data["phases"]
    ids = [p["id"] for p in phases]
    assert "capabilities" in ids
    assert "vault_layout" in ids
    assert "smoke" in ids
    assert data["docker"]["role"] == "runtime_after_bootstrap"
