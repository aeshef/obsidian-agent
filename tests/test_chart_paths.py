"""Chart path resolution from vault_paths.yaml."""
from __future__ import annotations

from pathlib import Path

from shared.chart_paths import chart_path, chart_wikilink_png, charts_root


def test_chart_path_includes_subfolder():
    vault = Path("/tmp/vault")
    p = chart_path(vault, "chart_daily_activity_png")
    assert "Планирование" in str(p)
    assert p.parent.parent == charts_root(vault)


def test_chart_wikilink_png_has_extension():
    link = chart_wikilink_png("chart_health_trends_png")
    assert link.endswith(".png]]")
    assert "Тренды_метрик.png" in link or "Trends" in link
