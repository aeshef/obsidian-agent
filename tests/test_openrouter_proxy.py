"""Tests for OpenRouter proxy env resolution."""
from __future__ import annotations

from shared.openrouter_proxy import openrouter_proxy_url, openrouter_requests_proxies


def test_openrouter_proxy_prefers_dedicated_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_PROXY", "socks5h://a:1")
    monkeypatch.setenv("YOUTUBE_PROXY", "socks5h://b:2")
    monkeypatch.setenv("HTTPS_PROXY", "http://c:3")
    assert openrouter_proxy_url() == "socks5h://a:1"


def test_openrouter_proxy_falls_back_to_youtube(monkeypatch):
    monkeypatch.delenv("OPENROUTER_PROXY", raising=False)
    monkeypatch.setenv("YOUTUBE_PROXY", "socks5h://b:2")
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    assert openrouter_proxy_url() == "socks5h://b:2"


def test_openrouter_requests_proxies_both_schemes(monkeypatch):
    monkeypatch.setenv("OPENROUTER_PROXY", "socks5h://127.0.0.1:1080")
    assert openrouter_requests_proxies() == {
        "http": "socks5h://127.0.0.1:1080",
        "https": "socks5h://127.0.0.1:1080",
    }


def test_openrouter_proxy_empty(monkeypatch):
    for key in ("OPENROUTER_PROXY", "YOUTUBE_PROXY", "HTTPS_PROXY", "HTTP_PROXY"):
        monkeypatch.delenv(key, raising=False)
    assert openrouter_proxy_url() is None
    assert openrouter_requests_proxies() is None
