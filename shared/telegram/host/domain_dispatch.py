"""Shim — use unified_bot.host.domain_dispatch."""
from unified_bot.host import domain_dispatch as _mod
globals().update({k: getattr(_mod, k) for k in dir(_mod) if not k.startswith('__')})
