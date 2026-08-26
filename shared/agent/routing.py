"""Deploy mode: single (unified_bot) only. Multi is unsupported."""
from __future__ import annotations

import logging
import os
import warnings

from shared.agent.types import Domain

log = logging.getLogger("shared.agent.routing")

_MULTI_WARNED = False


def deploy_mode() -> str:
    """Always ``single`` for supported installs.

    ``DEPLOY_MODE=multi`` is rejected with a warning and treated as single so
    clones cannot accidentally run three polling processes.
    """
    global _MULTI_WARNED
    raw = (os.environ.get("DEPLOY_MODE") or "single").strip().lower()
    if raw and raw != "single":
        if not _MULTI_WARNED:
            warnings.warn(
                f"DEPLOY_MODE={raw!r} is unsupported; forcing single (unified_bot).",
                UserWarning,
                stacklevel=2,
            )
            log.warning("DEPLOY_MODE=%s unsupported; forcing single", raw)
            _MULTI_WARNED = True
        return "single"
    return "single"


def resolve_domain(text: str, *, enabled: list[Domain] | None = None) -> Domain:
    """Removed multi-bot path — always raises (domain comes from unified agent)."""
    del text, enabled
    raise RuntimeError(
        "resolve_domain() is not used; free text goes to answer_unified / classify_host_domain_llm"
    )
