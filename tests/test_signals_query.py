"""Daily signals history formatting."""
from __future__ import annotations

from pathlib import Path


def test_format_daily_signals(tmp_path: Path, monkeypatch):
    hist = tmp_path / "Signals_History.md"
    hist.write_text(
        "# Signals\n\n"
        "## 2026-04-10\n\n```yaml\ndate: 2026-04-10\nsignals:\n  mood: 4\n```\n\n"
        "mood 4 · energy 3\n\n---\n\n"
        "## 2026-04-11\n\n```yaml\ndate: 2026-04-11\nsignals:\n  mood: 5\n```\n\n"
        "mood 5\n\n---\n\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "planning_bot.services.signals_query.signals_history_path",
        lambda: hist,
    )
    from planning_bot.services.signals_query import format_daily_signals

    out = format_daily_signals(from_date="2026-04-10", to_date="2026-04-11", limit=10)
    assert "2026-04-10" in out
    assert "2026-04-11" in out
