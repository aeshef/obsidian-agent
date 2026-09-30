"""Bound iCloud/FileProvider access so it cannot stall unrelated sync steps."""
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone
from shared.agent.config import agent_config_dir
from shared.yaml_config import load_merged_config

cfg=load_merged_config(str(agent_config_dir()),'health_backfill').get('queue_bridge',{})
try:
    result=subprocess.run([sys.executable,str(Path(__file__).with_name('health_queue_bridge.py'))],capture_output=True,text=True,timeout=cfg['local_timeout_seconds'])
    if result.returncode:
        report={'status':'degraded','error':'queue_worker_failed'}
    else:
        print(result.stdout.strip())
        raise SystemExit(0)
except subprocess.TimeoutExpired as exc:
    stages = (exc.stderr or b"").decode(errors="replace").splitlines()
    stage = next((line for line in reversed(stages) if line.startswith("queue_stage:")), "unknown")
    report={'status':'degraded','error':'icloud_access_timeout','stage':stage}
report['checked_at']=datetime.now(timezone.utc).isoformat()
path=Path(os.environ['VAULT_PATH'])/'.sync/health_queue_bridge.json'
path.parent.mkdir(parents=True,exist_ok=True)
temp=path.with_suffix('.tmp');temp.write_text(json.dumps(report));temp.replace(path)
print(json.dumps(report))
