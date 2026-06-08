"""Planning domain_messages keys that leaked Cyrillic through EN merge."""
from __future__ import annotations

from pathlib import Path

import yaml


def _flatten(d: object, prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], str]:
    out: dict[tuple[str, ...], str] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flatten(v, prefix + (str(k),)))
    else:
        out[prefix] = str(d)
    return out


def test_planning_logs_dir_keys_are_top_level():
    root = Path(__file__).resolve().parent.parent
    for name in ("domain_messages.en.yaml.example", "domain_messages.ru.yaml.example"):
        raw = yaml.safe_load((root / "config" / name).read_text(encoding="utf-8"))
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
            assert key in planning, f"{name}: planning.{key} missing"
        header = planning.get("log_month_header") or ""
        assert "logs_dir_access_denied" not in header
