"""Vault charts catalog + tools (no Cyrillic in assertions beyond vault fixtures)."""
from __future__ import annotations

from pathlib import Path

import pytest

from shared.charts_catalog import catalog_charts, format_catalog


def test_catalog_from_config_and_fs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    # Minimal vault_paths via env locale + example; create PNG under charts root.
    from shared.vault_paths_config import vault_paths_config, folder, dashboards_sub
    from shared.chart_paths import charts_root

    vault_paths_config.cache_clear()
    root = charts_root(tmp_path)
    root.mkdir(parents=True, exist_ok=True)
    # Put a discoverable PNG even if config keys point elsewhere
    sample = root / "Planning" / "sample_activity.png"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_bytes(b"\x89PNG\r\n\x1a\n")

    entries = catalog_charts(tmp_path, only_existing=True)
    assert any(e.rel_path.endswith("sample_activity.png") for e in entries)
    body = format_catalog(entries)
    assert "sample_activity" in body


@pytest.mark.asyncio
async def test_send_vault_charts_queues_media(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    from shared.vault_paths_config import vault_paths_config
    from shared.chart_paths import charts_root
    from shared.agent.chart_tools import send_vault_charts
    from shared.agent.types import AgentContext, CHART_MEDIA_EXTRAS_KEY

    vault_paths_config.cache_clear()
    root = charts_root(tmp_path)
    png = root / "Health" / "trends.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    png.write_bytes(b"\x89PNG\r\n\x1a\n")

    ctx = AgentContext(
        user_id=1,
        domain="planning",
        question="charts",
        system_prompt="",
        history=[],
        extras={},
    )
    out = await send_vault_charts(ctx, query="trends", limit=1)
    media = ctx.extras.get(CHART_MEDIA_EXTRAS_KEY) or []
    assert media, out
    assert media[0][0].endswith("trends.png")
