"""Shim — use unified_bot.host.keyboards."""
from unified_bot.host import keyboards as _mod
globals().update({k: getattr(_mod, k) for k in dir(_mod) if not k.startswith('__')})
