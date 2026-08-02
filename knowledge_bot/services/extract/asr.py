"""Compatibility shim — ASR lives in ``shared.asr``."""
from shared.asr import *  # noqa: F403
from shared.asr import transcribe_av  # noqa: F401 — explicit for type checkers
