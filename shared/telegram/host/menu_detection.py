"""Shim — use unified_bot.host.menu_detection."""
from unified_bot.host import menu_detection as _mod
globals().update({k: getattr(_mod, k) for k in dir(_mod) if not k.startswith('__')})
