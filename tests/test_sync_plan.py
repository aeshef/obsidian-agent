"""Python sync plan + lock helpers (OSS audit F13 carve)."""
from __future__ import annotations

from pathlib import Path

from shared.capabilities.presets import PRESET_KNOWLEDGE_ONLY, preset_document
from shared.capabilities.profile import profile_from_document
from shared.capabilities.sync_steps import STEP_KB_MAINTENANCE, STEP_FINANCE_DASHBOARD
from shared.sync import enabled_sync_steps, export_sync_plan_shell, plan_sync_steps
from shared.sync.lock import is_stale_lock, lock_age_seconds


def test_knowledge_only_plan_enables_kb():
    prof = profile_from_document(preset_document(PRESET_KNOWLEDGE_ONLY))
    enabled = enabled_sync_steps(prof)
    assert STEP_KB_MAINTENANCE in enabled
    assert STEP_FINANCE_DASHBOARD not in enabled


def test_export_sync_plan_shell_lines():
    prof = profile_from_document(preset_document(PRESET_KNOWLEDGE_ONLY))
    text = export_sync_plan_shell(prof)
    assert f"export {STEP_KB_MAINTENANCE}=1" in text
    assert f"export {STEP_FINANCE_DASHBOARD}=0" in text


def test_plan_covers_all_ordered_steps():
    plans = plan_sync_steps(profile_from_document(preset_document(PRESET_KNOWLEDGE_ONLY)))
    assert len(plans) >= 8
    assert all(hasattr(p, "enabled") for p in plans)


def test_lock_helpers(tmp_path: Path):
    lock = tmp_path / "lock"
    lock.mkdir()
    assert lock_age_seconds(lock) >= 0
    assert is_stale_lock(lock, stale_sec=10**9) is False
    assert is_stale_lock(lock, stale_sec=-1) is True
