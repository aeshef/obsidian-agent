"""Main extract_from_path orchestration."""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Optional

from knowledge_bot.services.extract._deps import easyocr, pytesseract
from knowledge_bot.services.extract.asr import transcribe_av
from knowledge_bot.services.extract.ocr import OcrProfile, extract_from_image
from knowledge_bot.services.extract.types import ExtractedBundle
from knowledge_bot.services.extract.vision import (
    _extract_video_middle_frame,
    extract_vision_from_video,
)
from knowledge_bot.services.extract.web import extract_from_pdf, simple_from_text

def extract_from_path(
    path_str: str,
    note_text: Optional[str] = None,
    llm_client: Optional[Any] = None,
    *,
    ocr_profile: OcrProfile = "photo",
) -> ExtractedBundle:
    path = Path(path_str)
    if not path.exists():
        return simple_from_text(note_text or path_str)
    suffix = path.suffix.lower()
    raw = note_text or f"[FILE] {str(path)}"
    
    vision_text = None
    ocr_text = None
    asr_text = None
    pdf_text = None
    
    if suffix in {".pdf"}:
        pdf_text = extract_from_pdf(path)
        return ExtractedBundle(raw_text=raw, urls=[], meta={"file": str(path)}, pdf_text=pdf_text)
    
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:

        log = logging.getLogger("kb.extract")
        ocr_text = extract_from_image(path, llm_client=llm_client, profile=ocr_profile)
        log.info("OCR for image: %d chars", len(ocr_text or ""))
        
        return ExtractedBundle(
            raw_text=raw, 
            urls=[], 
            meta={"file": str(path)}, 
            ocr_text=ocr_text,
            vision_text=None
        )
    
    if suffix in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:

        log = logging.getLogger("kb.extract")
        

        log.info("Starting ASR for video: %s", path.name)
        asr_text = transcribe_av(path)
        log.info("ASR completed: %d chars", len(asr_text or ""))
        

        ocr_text = ""
        mid_frame, ocr_tmpdir = _extract_video_middle_frame(path)
        if mid_frame and (pytesseract or easyocr):
            try:
                ocr_text = extract_from_image(mid_frame, llm_client=llm_client, profile="video_frame") or ""
                if ocr_text:
                    log.info("Video OCR (middle frame): %d chars", len(ocr_text))
            finally:
                if ocr_tmpdir and ocr_tmpdir.exists():
                    try:
                        shutil.rmtree(ocr_tmpdir, ignore_errors=True)
                    except Exception:
                        pass
        

        vision_text = ""
        if os.environ.get("OPENROUTER_API_KEY"):
            vision_text = extract_vision_from_video(path, asr_text=asr_text or "", llm_client=llm_client)
        
        return ExtractedBundle(
            raw_text=raw, 
            urls=[], 
            meta={"file": str(path)}, 
            asr_text=asr_text,
            ocr_text=ocr_text or "",
            vision_text=vision_text or None
        )
    
    if suffix in {".mp3", ".wav", ".m4a", ".aac", ".ogg"}:

        asr_text = transcribe_av(path)
        return ExtractedBundle(raw_text=raw, urls=[], meta={"file": str(path)}, asr_text=asr_text)
    
    # other types → just reference path
    return ExtractedBundle(raw_text=raw, urls=[], meta={"file": str(path)})
