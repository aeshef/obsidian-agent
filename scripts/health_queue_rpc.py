"""Validate and durably acknowledge Health packets; no email or LLM required."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


def accept_packets(packets, destination: Path):
    from planning_bot.tools.iphone_mail_sync import _parse_body, _snap_filename, _snap_to_txt
    from planning_bot.services.health_backfill import validate
    accepted, rejected = [], []
    destination.mkdir(parents=True, exist_ok=True)
    for packet in packets:
        body, digest = packet.get('body', ''), packet.get('sha256', '')
        if not isinstance(body, str) or hashlib.sha256(body.encode()).hexdigest() != digest:
            rejected.append({'sha256': digest, 'reason': 'checksum'})
            continue
        row = _parse_body(body)
        name = _snap_filename(row) if row else None
        if not row or not validate(row) or not name:
            rejected.append({'sha256': digest, 'reason': 'invalid_packet'})
            continue
        content = _snap_to_txt(row)
        target = destination/name
        if target.exists():
            if target.read_text() != content:
                rejected.append({'sha256': digest, 'reason': 'revision_conflict'})
                continue
        else:
            fd, temporary = tempfile.mkstemp(dir=destination, prefix='.packet-')
            try:
                with os.fdopen(fd, 'w') as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, target)
                directory_fd = os.open(destination, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                Path(temporary).unlink(missing_ok=True)
        accepted.append(digest)
    return {'accepted': accepted, 'rejected': rejected}


if __name__ == '__main__':
    from planning_bot.core.config import IPHONE_CONTEXT_DIR
    print(json.dumps(accept_packets(json.load(sys.stdin)['packets'], Path(IPHONE_CONTEXT_DIR))))
