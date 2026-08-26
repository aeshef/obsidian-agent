"""Re-export host router (guard against basename flatten duplicates)."""
from unified_bot.host.router import router

__all__ = ["router"]
