"""Tests for analytics hub layout."""
from __future__ import annotations

from pathlib import Path

from shared.analytics.hub_layout import render_analytics_hub


def test_hub_no_duplicate_png_in_overview(tmp_path: Path):
    vault = tmp_path
    (vault / "100_Задачи").mkdir()
    dash = vault / "300_Дашборды"
    (dash / "Графики" / "Аналитика").mkdir(parents=True)
    (dash / "Данные").mkdir()
    (dash / "Графики" / "Аналитика" / "Вес_динамика.png").write_bytes(b"x")

    body = render_analytics_hub(
        vault,
        ts="2026-01-01 12:00",
        msg=lambda k: k,
    )
    assert body.count("Вес_динамика.png") == 1
    assert "Корреляции_доменов" not in body
    assert "analytics_cross_health_link" in body or "health_dashboard" in body
