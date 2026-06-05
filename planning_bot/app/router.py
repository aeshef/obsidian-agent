"""Re-export host router (guard against basename flatten duplicates)."""
from shared.telegram.host.router import router

__all__ = ["router"]
