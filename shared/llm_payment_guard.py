"""Persist a short payment-error cooldown across scheduled worker processes."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import time
import requests
from shared.agent.config import agent_config_dir
from shared.yaml_config import load_merged_config


def _state(url, key):
    root = Path(os.environ.get('AGENT_ROOT', str(Path(__file__).resolve().parents[1])))
    identity = hashlib.sha256((url + '\0' + (key or '')).encode()).hexdigest()
    return root/'logs'/'llm_payment'/f'{identity}.json'


def check(url, key):
    try:
        state = json.loads(_state(url, key).read_text())
    except (OSError, ValueError):
        return
    if state.get('retry_after', 0) > time.time():
        response = requests.Response()
        response.status_code = 402
        raise requests.HTTPError('LLM payment cooldown; retry after provider balance is restored', response=response)


def record(url, key, status):
    if 200 <= status < 300:
        try:
            _state(url, key).unlink(missing_ok=True)
        except OSError:
            pass
        return
    if status != 402:
        return
    cfg = load_merged_config(str(agent_config_dir()), 'llm_reliability')
    if not cfg.get('payment_cooldown_seconds'):
        return
    path = _state(url, key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(f'.{os.getpid()}.tmp')
        temp.write_text(json.dumps({'status': 402, 'observed_at': time.time(), 'retry_after': time.time()+cfg['payment_cooldown_seconds']}))
        temp.replace(path)
    except OSError:
        # Failure to record a cooldown must not mask the provider's error.
        pass
