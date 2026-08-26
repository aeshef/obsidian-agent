"""Shim — use unified_bot.host.message_proxy."""
from unified_bot.host import message_proxy as _mod
globals().update({k: getattr(_mod, k) for k in dir(_mod) if not k.startswith('__')})
