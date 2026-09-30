"""GitHub community files present in the public tree."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_github_hygiene_files():
    required = [
        "LICENSE",
        "README.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        "SUPPORT.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/dependabot.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/ISSUE_TEMPLATE/bug_report.md",
        ".github/workflows/ci.yml",
    ]
    missing = [p for p in required if not (ROOT / p).is_file()]
    assert not missing, f"missing GitHub hygiene files: {missing}"


def test_issue_template_config():
    path = ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data.get("blank_issues") is False
    links = data.get("contact_links") or []
    assert any("discussions" in str(x.get("url", "")).lower() for x in links)
    assert any("security" in str(x.get("name", "")).lower() for x in links)
