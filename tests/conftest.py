"""Shared fixtures for integration tests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
