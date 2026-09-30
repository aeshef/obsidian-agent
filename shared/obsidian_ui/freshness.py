"""Freshness of rendered datasets, independent of source collection health."""
import json
from datetime import datetime
from pathlib import Path
from shared.obsidian_ui.config import ui_config
from shared.vault_paths_config import folder, dashboards_sub
from shared.capabilities.profile import get_capabilities


def dataset_status(vault: Path, now: datetime) -> dict:
    cfg = ui_config()
    root = vault / folder('dashboards') / dashboards_sub('data') / cfg['layout']['view_root']
    profile = get_capabilities()
    kinds = []
    if profile.module('planning'):
        kinds += ['progress', 'analytics']
        if profile.connector('apple_health'): kinds.append('health')
        if profile.connector('apple_calendar'): kinds.append('calendar')
    if profile.module('finance'): kinds.append('finance')
    result = {}
    for kind in kinds:
        try:
            data = json.loads((root / (kind + '.json')).read_text())
            ts = datetime.fromisoformat(data['generated_at'].replace('Z', '+00:00'))
            if ts.tzinfo is None: raise ValueError('timezone_missing')
            age = (now - ts).total_seconds()
            limit = cfg['freshness']['daily_seconds'] if kind == 'analytics' else cfg['freshness']['max_age_seconds']
            result[kind] = {'status': 'invalid_clock' if age < 0 else 'stale' if age > limit else 'ok', 'generated_at':data['generated_at'], 'age_seconds':round(age)}
        except FileNotFoundError:
            result[kind] = {'status': 'missing'}
        except (OSError, ValueError, KeyError, TypeError):
            result[kind] = {'status': 'invalid'}
    return result
