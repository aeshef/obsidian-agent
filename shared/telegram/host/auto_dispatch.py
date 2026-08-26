"""Shim — use unified_bot.host.auto_dispatch."""
from unified_bot.host import auto_dispatch as _mod
globals().update({k: getattr(_mod, k) for k in dir(_mod) if not k.startswith('__')})
