"""Dynamic prompt supplements when @cap blocks are absent."""
from __future__ import annotations

from shared.capabilities.profile import clear_capabilities_cache
from shared.capabilities.prompt_preamble import augment_prompt_capabilities


def test_augment_skips_when_cap_blocks_present(monkeypatch):
    monkeypatch.delenv("CAP_CONNECTOR_BROKER_SYNC", raising=False)
    clear_capabilities_cache()
    text = "Base\n<!-- @cap broker -->\nB\n<!-- @/cap -->"
    assert augment_prompt_capabilities("host_query", text) == text
    clear_capabilities_cache()


def test_augment_appends_enabled_lines(monkeypatch):
    monkeypatch.setenv("CAP_CONNECTOR_BROKER_SYNC", "1")
    monkeypatch.setenv("CAP_MODULE_FINANCE", "1")
    clear_capabilities_cache()
    out = augment_prompt_capabilities("host_query", "You are the host.")
    assert "[Enabled capabilities]" in out
    assert "Broker portfolio" in out
    clear_capabilities_cache()


def test_augment_empty_when_all_off(monkeypatch):
    monkeypatch.setenv("CAP_MODULE_FINANCE", "0")
    monkeypatch.setenv("CAP_MODULE_PLANNING", "0")
    monkeypatch.setenv("CAP_MODULE_KNOWLEDGE", "0")
    monkeypatch.setenv("CAP_CONNECTOR_BROKER_SYNC", "0")
    monkeypatch.setenv("CAP_CONNECTOR_APPLE_HEALTH", "0")
    clear_capabilities_cache()
    out = augment_prompt_capabilities("host_query", "Base prompt.")
    assert out == "Base prompt."
    clear_capabilities_cache()
