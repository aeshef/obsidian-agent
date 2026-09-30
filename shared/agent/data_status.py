"""Honest read-only source coverage; disabled connectors never leak into status."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from shared.agent.tools import tool
from shared.agent.types import AgentContext
from shared.capabilities.profile import get_capabilities
from shared.agent.platform_config import platform_int
from shared.i18n import msg, msgf

SOURCE_CONNECTORS = {"iphone": "apple_health", "calendar": "apple_calendar", "mac": "mac_context", "broker": "broker_sync"}


def read_status():
    prof=get_capabilities(); root=Path(os.environ.get("VAULT_PATH", "."))
    try: report=json.loads((root/".sync/pipeline_health.json").read_text())
    except (OSError, ValueError): return {"status":"unknown","sources":{}}
    stamp=report.get("checked_at") or report.get("generated_at")
    try:
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(stamp.replace("Z","+00:00"))).total_seconds()
        stale=age>platform_int("data_status","max_report_age_seconds",default=3600)
    except (ValueError,TypeError,AttributeError): stale=True
    sources={k:v for k,v in report.get("sources",{}).items() if k in SOURCE_CONNECTORS and prof.connector(SOURCE_CONNECTORS[k])}
    queue={}
    if prof.connector("apple_health"):
        try:
            q=json.loads((root/".sync/health_queue_bridge.json").read_text())
            queue={k:q[k] for k in ("checked_at","status","pending") if k in q}
        except (OSError,ValueError): pass
    return {"status":"unknown" if stale else report.get("status","unknown"),"checked_at":stamp,"sources":sources,"queue":queue,"health_coverage":report.get("health_coverage", {}) if prof.connector("apple_health") else {},"scope":"Freshness of received data; not proof of complete measurements or permission on the phone."}


def render_status():
    data=read_status(); lines=[msg("host", "data_status_"+data["status"])]
    for name, source in data["sources"].items():
        lines.append(msgf("host","data_source_row",source=msg("host","data_source_"+name),status=source.get("status","unknown"),date=source.get("captured_at") or msg("host","data_date_unknown")))
    if "pending" in data.get("queue",{}):lines.append(msgf("host","data_queue",count=data["queue"]["pending"]))
    for group, day in data.get("health_coverage",{}).items():
        lines.append(msgf("host","data_group_row",group=msg("host","data_group_"+group,default=group),date=day or msg("host","data_date_unknown")))
    lines.append(msg("host","data_scope"))
    return "\n".join(lines)


@tool(category="system", read_only=True)
async def get_data_status(ctx: AgentContext) -> str:
    """What data do you know about me: latest received source timestamps, pending delivery and missing freshness. Does NOT prove completeness of sleep or nutrition."""
    return json.dumps(read_status(),ensure_ascii=False)
