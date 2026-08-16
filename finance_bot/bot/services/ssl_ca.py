"""TLS CA bundle: Mozilla (certifi) + Russian Trusted Root/Sub (MinTsifry).

T-Bank Invest API presents Russian Trusted chain; stock certifi alone fails verify.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("finance.ssl_ca")

_CERTS_DIR = Path(__file__).resolve().parents[2] / "certs"
_RU_PEMS = (
    "russian_trusted_root_ca.pem",
    "russian_trusted_sub_ca.pem",
)


@lru_cache(maxsize=1)
def httpx_verify_path() -> str | bool:
    """Path for httpx ``verify=`` (combined bundle), or True for defaults."""
    try:
        import certifi
    except Exception:
        return True
    ru_paths = [_CERTS_DIR / name for name in _RU_PEMS]
    if not all(p.is_file() for p in ru_paths):
        log.warning("Russian Trusted CA PEMs missing under %s — using certifi only", _CERTS_DIR)
        return certifi.where()

    out = _CERTS_DIR / "ca_bundle_mozilla_ru_trusted.pem"
    try:
        parts = [Path(certifi.where()).read_bytes()]
        for p in ru_paths:
            parts.append(b"\n")
            parts.append(p.read_bytes())
        data = b"".join(parts)
        if not out.is_file() or out.read_bytes() != data:
            out.write_bytes(data)
        return str(out)
    except OSError as e:
        log.warning("failed to build CA bundle: %s", e)
        return certifi.where()


def httpx_client_kwargs(**extra) -> dict:
    """Kwargs for ``httpx.Client`` / ``AsyncClient`` with RU-capable verify."""
    kw = {"verify": httpx_verify_path(), "follow_redirects": True}
    kw.update(extra)
    return kw
