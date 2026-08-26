"""Planning domain_messages keys that leaked Cyrillic through EN merge."""
from __future__ import annotations

from shared.domain_messages import load_domain_packages


def test_planning_logs_dir_keys_are_top_level():
    for locale in ("en", "ru"):
        raw = load_domain_packages(locale)
        planning = raw.get("planning") or {}
        for key in (
            "logs_dir_access_denied",
            "logs_dir_empty",
            "logs_dir_missing",
            "logs_dir_not_dir",
            "calendar_chat_header",
            "calendar_prompt_status_empty",
            "calendar_prompt_status_ok",
        ):
            assert key in planning, f"{locale} packages: planning.{key} missing"
        header = planning.get("log_month_header") or ""
        assert "logs_dir_access_denied" not in header
