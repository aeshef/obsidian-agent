"""Server-side Health mail intake independent of a running Mac."""
import json
from pathlib import Path
from datetime import datetime,timezone
from shared.capabilities.sync_steps import sync_step_enabled, STEP_GMAIL_HEALTH


def run():
    if not sync_step_enabled(STEP_GMAIL_HEALTH):
        return {'status':'disabled'}
    from planning_bot.tools.iphone_mail_sync import run_iphone_mail_sync
    from planning_bot.tools.iphone_context_sync import run_iphone_context_sync
    from planning_bot.core.config import VAULT_PATH
    result=run_iphone_mail_sync(today_only=False)
    aggregated=run_iphone_context_sync()
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'status':'ok' if result.get('ok') and aggregated else 'degraded','written':result.get('written',0),'rejected':result.get('rejected',0),'errors':len(result.get('errors',[]))}
    target=Path(VAULT_PATH)/'.sync/health_mail_worker.json';target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(report));tmp.replace(target)
    return report

if __name__=='__main__':
    result=run();print(json.dumps(result));raise SystemExit(1 if result['status']=='degraded' else 0)
