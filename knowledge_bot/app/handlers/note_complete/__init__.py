"""Knowledge ingest pipeline: media → extract → review."""
from knowledge_bot.app.handlers.note_complete.complete import process_complete

__all__ = ["process_complete"]
