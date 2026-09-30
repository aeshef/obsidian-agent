"""Supplement iPhone Mail with acknowledged delivery from its iCloud outbox."""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from datetime import datetime, timezone

from shared.agent.config import agent_config_dir
from shared.yaml_config import load_merged_config


def run():
    from shared.capabilities.profile import get_capabilities
    cfg = load_merged_config(str(agent_config_dir()), 'health_backfill').get('queue_bridge', {})
    if not get_capabilities().connector('apple_health') or not cfg.get('enabled') or sys.platform != 'darwin':
        return {'status': 'disabled'}
    print('queue_stage: configure', file=sys.stderr, flush=True)
    root = Path(cfg['directory']).expanduser()
    state = Path(os.environ['VAULT_PATH'])/'.sync'
    state.mkdir(parents=True, exist_ok=True)
    with (state/'health_queue_bridge.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 'busy'}
        print('queue_stage: list_icloud', file=sys.stderr, flush=True)
        packets, paths, errors = [], {}, []
        for path in sorted((root/'Outbox').glob('*.txt'))[:cfg['batch_size']]:
            try:
                print('queue_stage: read_icloud', file=sys.stderr, flush=True)
                body = path.read_text()
                digest = hashlib.sha256(body.encode()).hexdigest()
                packets.append({'sha256': digest, 'body': body})
                paths[digest] = path
            except OSError as exc:
                errors.append(f'unreadable_file:{type(exc).__name__}:{exc.errno}')
        accepted = []
        if packets:
            print('queue_stage: deliver', file=sys.stderr, flush=True)
            command = 'cd ' + shlex.quote(os.environ['SERVER_BOTS']) + ' && ./scripts/oa-python.sh scripts/health_queue_rpc.py'
            response = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', os.environ['SERVER'], command], input=json.dumps({'packets': packets}), capture_output=True, text=True, timeout=cfg['timeout_seconds'])
            if response.returncode:
                raise RuntimeError('health_queue_transport_failed')
            result = json.loads(response.stdout)
            accepted = result['accepted']
            if not set(accepted) <= paths.keys():
                raise ValueError('invalid_ack')
            errors.extend(item['reason'] for item in result.get('rejected', []))
            # Existing rsync treats the Mac raw-snapshot directory as authoritative.
            # Persist the same revisions locally before allowing a later --delete push.
            from planning_bot.core.config import IPHONE_CONTEXT_DIR
            from scripts.health_queue_rpc import accept_packets
            local = accept_packets([packet for packet in packets if packet['sha256'] in accepted], Path(IPHONE_CONTEXT_DIR))
            accepted = local['accepted']
            errors.extend(item['reason'] for item in local['rejected'])
            archive = root/'ServerAccepted'
            archive.mkdir(exist_ok=True)
            for digest in accepted:
                path = paths[digest]
                try:
                    # iPhone may have moved/replaced the file while the RPC was running.
                    if hashlib.sha256(path.read_bytes()).hexdigest() == digest:
                        os.replace(path, archive/(digest+'.txt'))
                except FileNotFoundError:
                    pass
        print('queue_stage: status', file=sys.stderr, flush=True)
        report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'degraded' if errors else 'ok', 'accepted': len(accepted), 'pending': len(list((root/'Outbox').glob('*.txt'))), 'errors': errors}
        target = state/'health_queue_bridge.json'
        temporary = target.with_suffix('.tmp'); temporary.write_text(json.dumps(report)); temporary.replace(target)
        return report


if __name__ == '__main__':
    print(json.dumps(run()))
