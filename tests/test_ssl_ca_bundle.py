"""Russian Trusted CA bundle for T-Bank Invest TLS."""
from __future__ import annotations

from pathlib import Path


def test_russian_trusted_pems_present():
    certs = Path(__file__).resolve().parents[1] / "finance_bot" / "certs"
    assert (certs / "russian_trusted_root_ca.pem").is_file()
    assert (certs / "russian_trusted_sub_ca.pem").is_file()
    root = (certs / "russian_trusted_root_ca.pem").read_text(encoding="utf-8")
    assert "BEGIN CERTIFICATE" in root


def test_httpx_verify_path_includes_ru_ca(tmp_path, monkeypatch):
    from bot.services import ssl_ca

    ssl_ca.httpx_verify_path.cache_clear()
    path = ssl_ca.httpx_verify_path()
    assert isinstance(path, str)
    data = Path(path).read_text(encoding="utf-8")
    assert "BEGIN CERTIFICATE" in data
    # Combined bundle should be larger than either RU PEM alone.
    root_len = len((ssl_ca._CERTS_DIR / "russian_trusted_root_ca.pem").read_bytes())
    assert len(data) > root_len + 1000
    ssl_ca.httpx_verify_path.cache_clear()
