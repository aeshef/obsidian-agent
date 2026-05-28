"""Optional third-party imports and EasyOCR singleton."""
from __future__ import annotations

import logging


def _safe_import(name: str):
    try:
        return __import__(name)
    except Exception:
        return None


trafilatura = _safe_import("trafilatura")
pdfminer = _safe_import("pdfminer.high_level")
PIL = _safe_import("PIL")
pytesseract = _safe_import("pytesseract")
easyocr = _safe_import("easyocr")
requests = _safe_import("requests")
yt_dlp = _safe_import("yt_dlp")
yt_transcript_api = _safe_import("youtube_transcript_api")

_easyocr_reader = None
_easyocr_reader_lock = None


def _get_easyocr_reader():
    """Extract helper."""
    global _easyocr_reader, _easyocr_reader_lock
    log = logging.getLogger("kb.extract")

    if easyocr is None:
        log.info("EasyOCR module not available")
        return None

    if _easyocr_reader is None:
        try:
            log.info("Initializing EasyOCR reader (this may take 30-60 seconds on first run)...")
            _easyocr_reader = easyocr.Reader(["en", "ru"], gpu=False, verbose=False)
            log.info("EasyOCR reader initialized successfully")
        except Exception as e:
            log.error("Failed to initialize EasyOCR reader: %s", e, exc_info=True)
            _easyocr_reader = False  # Mark as failed to avoid retrying

    return _easyocr_reader if _easyocr_reader is not False else None


_log = logging.getLogger("kb.extract")
if pytesseract:
    _log.info("Tesseract OCR: available")
else:
    _log.warning("Tesseract OCR: NOT available (pytesseract not installed)")

if easyocr:
    _log.info("EasyOCR: module imported successfully (reader will be initialized on first use)")
else:
    _log.warning("EasyOCR: NOT available (easyocr not installed)")
