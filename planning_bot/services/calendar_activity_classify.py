"""LLM-assign calendar activity_type onto events (cached on the event dict)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Tuple

from planning_bot.services.calendar_analytics import (
    activity_signature,
    activity_type_descriptions,
    allowed_activity_types,
    classify_activity,
)
from shared.agent.llm_classify import LLMClassificationError, classify_calendar_activities_llm
from shared.agent.platform_config import platform_int

log = logging.getLogger(__name__)


def _needs_classify(ev: Dict[str, Any], allowed: set[str]) -> bool:
    if ev.get("is_cancelled"):
        return False
    raw = str(ev.get("activity_type") or "").strip()
    if not raw or raw not in allowed:
        return True
    sig = ev.get("activity_sig")
    return sig != activity_signature(ev)


def ensure_activity_types(
    events: List[Dict[str, Any]],
    *,
    force: bool = False,
) -> Tuple[List[Dict[str, Any]], int]:
    """Classify missing/stale activity_type via LLM. Mutates events in place.

    Returns (events, classified_count). Raises LLMClassificationError on failure
    when there is work to do — callers decide whether to abort sync.
    """
    allowed = allowed_activity_types()
    pending = [
        ev
        for ev in events
        if ev.get("id") and (force or _needs_classify(ev, allowed))
    ]
    if not pending:
        return events, 0

    batch = max(1, platform_int("llm_classify", "calendar_activity_batch", default=40))
    taxonomy = activity_type_descriptions()
    if not taxonomy:
        taxonomy = {t: t for t in sorted(allowed)}

    classified = 0
    for i in range(0, len(pending), batch):
        chunk = pending[i : i + batch]
        mapping = asyncio.run(
            classify_calendar_activities_llm(
                chunk, taxonomy=taxonomy, allowed=allowed
            )
        )
        by_id = {str(ev["id"]): ev for ev in chunk}
        for eid, typ in mapping.items():
            ev = by_id.get(eid)
            if ev is None:
                continue
            ev["activity_type"] = typ
            ev["activity_sig"] = activity_signature(ev)
            classified += 1

    log.info(
        "calendar activity ensure: classified=%s pending=%s total=%s",
        classified,
        len(pending),
        len(events),
    )
    # Touch classify path so default-only callers see fresh labels.
    for ev in events:
        if ev.get("activity_type"):
            classify_activity(ev)
    return events, classified
