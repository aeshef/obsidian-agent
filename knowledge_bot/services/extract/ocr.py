"""OCR engines (Tesseract + EasyOCR) for images and video."""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Any, Literal, Optional

from knowledge_bot.services.extract._deps import PIL, easyocr, pytesseract, _get_easyocr_reader

OcrProfile = Literal["thumbnail", "photo", "video_frame"]


def _ocr_easyocr_enabled() -> bool:
    return os.environ.get("OCR_EASYOCR", "1").strip().lower() not in ("0", "false", "no", "off")


def _tesseract_sufficient_chars() -> int:
    try:
        return max(1, int(os.environ.get("OCR_TESSERACT_SUFFICIENT_CHARS", "40")))
    except ValueError:
        return 40


def _should_run_easyocr(path: Path, tesseract_text: str) -> bool:
    """Extract helper."""
    log = logging.getLogger("kb.extract")
    if not easyocr or not _ocr_easyocr_enabled():
        return False
    tess = (tesseract_text or "").strip()
    min_chars = _tesseract_sufficient_chars()
    if len(tess) >= min_chars:
        log.info(
            "Skipping EasyOCR: Tesseract already %d chars (>= %d)",
            len(tess),
            min_chars,
        )
        return False
    if PIL and tess:
        try:
            w, h = PIL.Image.open(path).size
            if max(w, h) <= 400:
                log.info(
                    "Skipping EasyOCR on small image %dx%d (Tesseract=%d chars)",
                    w,
                    h,
                    len(tess),
                )
                return False
        except Exception:
            pass
    return True


def _resize_if_smaller(img: "PIL.Image.Image", max_dim: int) -> "PIL.Image.Image":
    """Extract helper."""
    width, height = img.size
    if max(width, height) >= max_dim:
        return img
    scale = max_dim / max(width, height, 1)
    new_size = (int(width * scale), int(height * scale))
    return img.resize(new_size, PIL.Image.LANCZOS)


def _ocr_tesseract_thumbnail(img: "PIL.Image.Image") -> str:
    """Extract helper."""
    if pytesseract is None:
        return ""
    try:
        from PIL import ImageEnhance, ImageOps

        if img.mode != "RGB":
            img = img.convert("RGB")
        img = _resize_if_smaller(img, max_dim=960)
        gray = ImageOps.autocontrast(img.convert("L"), cutoff=1)
        gray = ImageEnhance.Contrast(gray).enhance(1.6)
        return (
            pytesseract.image_to_string(gray, lang="eng+rus", config="--psm 6 --oem 3") or ""
        ).strip()
    except Exception as e:
        logging.getLogger("kb.extract").warning("Tesseract thumbnail OCR failed: %s", e)
        return ""


def _ocr_tesseract(img: PIL.Image.Image, *, profile: OcrProfile = "photo") -> str:
    """Extract helper."""
    if profile == "thumbnail":
        return _ocr_tesseract_thumbnail(img)
    return _ocr_tesseract_full(img)


def _ocr_tesseract_full(img: PIL.Image.Image) -> str:
    if pytesseract is None:
        return ""
    try:
        from PIL import ImageEnhance, ImageFilter, ImageOps
        try:
            import numpy as np
            from scipy import ndimage
            has_scipy = True
        except ImportError:
            has_scipy = False
        try:
            import numpy as np
            has_numpy = True
        except ImportError:
            has_numpy = False
        
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        width, height = img.size
        max_dim = 2200
        if max(width, height) < max_dim:
            scale = max_dim / max(width, height, 1)
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, PIL.Image.LANCZOS)
        
        gray = img.convert('L')
        
        if has_scipy:
            try:
                img_array = np.array(gray)
                img_array = ndimage.median_filter(img_array, size=3)
                gray = PIL.Image.fromarray(img_array, mode='L')
            except Exception:
                pass
        
        gray = ImageOps.autocontrast(gray, cutoff=1)
        
        enhancer = ImageEnhance.Contrast(gray)
        gray = enhancer.enhance(2.0)
        
        enhancer = ImageEnhance.Sharpness(gray)
        gray = enhancer.enhance(1.5)
        
        results = []
        
        if has_scipy and has_numpy:
            try:
                from skimage.filters import threshold_otsu
                img_array = np.array(gray)
                threshold = threshold_otsu(img_array)
                binary = (img_array > threshold).astype(np.uint8) * 255
                binary_img = PIL.Image.fromarray(binary, mode='L')
                
                for psm in ['6', '7', '11', '3', '12']:
                    try:
                        from knowledge_bot.i18n.domain_text import cyrillic_ocr_whitelist

                        whitelist = (
                            "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                            + cyrillic_ocr_whitelist()
                            + ".,!?;:()[]{{}}\\'\"- "
                        )
                        txt = pytesseract.image_to_string(
                            binary_img,
                            lang='eng+rus',
                            config=f'--psm {psm} --oem 3 -c tessedit_char_whitelist={whitelist}'
                        ) or ""
                        if txt.strip():
                            results.append((len([c for c in txt if c.isalnum()]), txt))
                    except Exception:
                        pass
            except ImportError:
                if has_numpy:
                    try:
                        img_array = np.array(gray)
                        threshold = np.mean(img_array)
                        binary = (img_array > threshold).astype(np.uint8) * 255
                        binary_img = PIL.Image.fromarray(binary, mode='L')
                        
                        for psm in ['6', '7', '11', '3', '12']:
                            try:
                                txt = pytesseract.image_to_string(
                                    binary_img,
                                    lang='eng+rus',
                                    config=f'--psm {psm} --oem 3'
                                ) or ""
                                if txt.strip():
                                    results.append((len([c for c in txt if c.isalnum()]), txt))
                            except Exception:
                                pass
                    except Exception:
                        pass
        
        for psm in ['6', '7', '11', '3', '12']:
            try:
                txt = pytesseract.image_to_string(
                    gray,
                    lang='eng+rus',
                    config=f'--psm {psm} --oem 3'
                ) or ""
                if txt.strip():
                    results.append((len([c for c in txt if c.isalnum()]), txt))
            except Exception:
                pass
        
        if results:
            results.sort(reverse=True, key=lambda x: x[0])
            return results[0][1]
        
        return ""
    except Exception as e:
        logging.getLogger("kb.extract").warning("Tesseract OCR failed: %s", e)
        return ""


def _easyocr_timeout_sec() -> float:
    try:
        return max(10.0, float(os.environ.get("OCR_EASYOCR_TIMEOUT_SEC", "120")))
    except ValueError:
        return 120.0


def _ocr_easyocr(img_path: str, *, max_output_dim: int = 1600) -> str:
    """Extract helper."""
    log = logging.getLogger("kb.extract")

    reader = _get_easyocr_reader()
    if reader is None:
        return ""

    tmp_path_to_cleanup = None
    original_img_path = img_path
    try:
        if PIL:
            try:
                from PIL import ImageEnhance, ImageOps

                img = PIL.Image.open(img_path)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img = _resize_if_smaller(img, max_output_dim)
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    tmp_path_to_cleanup = tmp.name
                    img.save(tmp_path_to_cleanup, "JPEG", quality=92)
                img_path = tmp_path_to_cleanup
            except Exception as preprocess_err:
                log.debug("EasyOCR preprocess failed, using original: %s", preprocess_err)

        timeout = _easyocr_timeout_sec()
        t0 = time.monotonic()

        def _read():
            return reader.readtext(img_path)

        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_read)
            try:
                results = fut.result(timeout=timeout)
            except FuturesTimeout:
                log.warning("EasyOCR readtext timed out after %.0fs (%s)", timeout, img_path)
                return ""

        log.info("EasyOCR readtext %.1fs", time.monotonic() - t0)
        
        lines = []
        confidences = []
        for (bbox, text, confidence) in results:
            confidences.append(confidence)
            if confidence > 0.4:
                text_clean = text.strip()
                if len(text_clean) > 1 and any(c.isalnum() for c in text_clean):
                    lines.append(text_clean)
        
        result = '\n'.join(lines)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        log.info("EasyOCR: %d chars extracted from %d detections, confidence avg=%.2f (min=%.2f, max=%.2f)", 
                len(result), len(results), avg_confidence,
                min(confidences) if confidences else 0.0,
                max(confidences) if confidences else 0.0)
        
        return result
    except Exception as e:
        log.error("EasyOCR failed: %s", e, exc_info=True)
        return ""
    finally:
        if tmp_path_to_cleanup and tmp_path_to_cleanup != original_img_path:
            try:
                os.unlink(tmp_path_to_cleanup)
            except Exception:
                pass


def _merge_ocr_results(tesseract_text: str, easyocr_text: str) -> str:
    """Merge Tesseract + EasyOCR text, dropping exact duplicate lines."""
    log = logging.getLogger("kb.extract")
    
    if not tesseract_text and not easyocr_text:
        return ""
    
    if not tesseract_text:
        log.info("Merged OCR: Only EasyOCR result (%d chars)", len(easyocr_text))
        return easyocr_text
    if not easyocr_text:
        log.info("Merged OCR: Only Tesseract result (%d chars)", len(tesseract_text))
        return tesseract_text
    
    tess_lines = [l.strip() for l in tesseract_text.splitlines() if l.strip()]
    easy_lines = [l.strip() for l in easyocr_text.splitlines() if l.strip()]
    
    log.debug("Merging OCR: Tesseract=%d lines, EasyOCR=%d lines", len(tess_lines), len(easy_lines))
    
    merged = []
    seen_normalized = set()
    
    all_lines = []
    for line in tess_lines:
        all_lines.append(('tess', line))
    for line in easy_lines:
        all_lines.append(('easy', line))
    
    for source, line in all_lines:
        line_normalized = line.lower().strip()
        
        if not line_normalized:
            continue
        
        if line_normalized in seen_normalized:
            continue
        
        is_similar = False
        line_words = set(line_normalized.split())
        
        for existing_line in merged:
            existing_words = set(existing_line.lower().split())
            if len(line_words) == 0 or len(existing_words) == 0:
                continue
            
            intersection = line_words & existing_words
            union = line_words | existing_words
            
            if len(union) > 0:
                similarity = len(intersection) / len(union)
                if similarity > 0.8 and len(line) > len(existing_line):
                    log.debug("Replacing similar line (similarity=%.2f): '%s' -> '%s'", 
                             similarity, existing_line[:50], line[:50])
                    merged.remove(existing_line)
                    seen_normalized.discard(existing_line.lower().strip())
                    break
                elif similarity > 0.8:
                    is_similar = True
                    break
        
        if not is_similar:
            merged.append(line)
            seen_normalized.add(line_normalized)
    
    result = '\n'.join(merged)
    log.info("Merged OCR: Tesseract=%d chars (%d lines), EasyOCR=%d chars (%d lines), Merged=%d chars (%d unique lines)", 
             len(tesseract_text), len(tess_lines), len(easyocr_text), len(easy_lines), len(result), len(merged))
    return result


def extract_from_image(
    path: Path,
    llm_client: Optional[Any] = None,
    *,
    profile: OcrProfile = "photo",
) -> str:
    """Extract helper."""
    log = logging.getLogger("kb.extract")
    if PIL is None:
        log.info("Pillow not installed; skip OCR: %s", path)
        return ""

    if pytesseract is None and easyocr is None:
        log.info("No OCR engines available; skip OCR: %s", path)
        return ""

    t_total = time.monotonic()
    try:
        img = PIL.Image.open(str(path))
        w, h = img.size
        log.info("OCR profile=%s size=%dx%d path=%s", profile, w, h, path.name)

        tesseract_text = ""
        easyocr_text = ""

        if pytesseract:
            t0 = time.monotonic()
            tesseract_text = _ocr_tesseract(img, profile=profile)
            log.info("Tesseract OCR: %d chars in %.1fs", len(tesseract_text), time.monotonic() - t0)

        if profile != "thumbnail" and _should_run_easyocr(path, tesseract_text):
            log.info("Starting EasyOCR for image...")
            t0 = time.monotonic()
            easyocr_text = _ocr_easyocr(str(path))
            log.info(
                "EasyOCR: %d chars in %.1fs",
                len(easyocr_text or ""),
                time.monotonic() - t0,
            )
        elif profile == "thumbnail":
            log.info("Thumbnail profile: EasyOCR skipped by design")

        merged = _merge_ocr_results(tesseract_text, easyocr_text)
        result = merged
        log.info(
            "extract_from_image: final len=%d total %.1fs %s",
            len(result or ""),
            time.monotonic() - t_total,
            path.name,
        )

        if profile == "photo" and llm_client and result and len(result) > 50:
            try:
                import json
                try:
                    from knowledge_bot.core.config import load_config
                    cfg = load_config()
                    from knowledge_bot.core.settings import load_prompt
                    ocr_clean_prompt = load_prompt(cfg.agent_config_path, "ocr_clean")
                except Exception:
                    prompt_path = Path(__file__).parent / "config" / "prompts" / "ocr_clean.txt"
                    if prompt_path.exists():
                        ocr_clean_prompt = prompt_path.read_text(encoding="utf-8")
                    else:
                        ocr_clean_prompt = None
                
                if ocr_clean_prompt:
                    user_input = ocr_clean_prompt.replace("{ocr_text}", result)
                    cleaned = llm_client.chat("", user_input).content or result
                    cleaned_strip = cleaned.strip()
                    from knowledge_bot.i18n.domain_text import ocr as ocr_msg

                    absent = ocr_msg("text_absent").lower()
                    absent_br = ocr_msg("text_absent_bracket").lower()
                    low = cleaned_strip.lower()
                    if absent in low or absent_br in low:
                        log.info("LLM OCR cleanup: rejected as noise, keeping empty")
                        return ""
                    if cleaned_strip and len(cleaned_strip) > len(result.strip()) * 0.5:
                        log.info("LLM cleaned OCR: %d -> %d chars", len(result), len(cleaned_strip))
                        return cleaned_strip
            except Exception as llm_err:
                log.warning("LLM OCR cleanup failed: %s", llm_err)
        
        return result
    except Exception as e:
        log.warning("extract_from_image failed: %s", e)
        return ""


def extract_ocr_from_video(path: Path, frame_interval: float = 1.0, llm_client: Optional[Any] = None) -> str:
    """OCR sampled video frames (not every frame); returns merged text."""
    log = logging.getLogger("kb.extract")
    if PIL is None:
        log.info("Pillow not installed; skip video OCR: %s", path)
        return ""
    
    if pytesseract is None and easyocr is None:
        log.info("No OCR engines available; skip video OCR: %s", path)
        return ""
    
    try:
        import tempfile
        fps = 1.0 / frame_interval
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            frame_pattern = str(tmpdir_path / "frame_%04d.jpg")
            cmd = [
                "ffmpeg", "-y", "-i", str(path),
                "-vf", f"fps={fps:.3f},scale=3000:-1,unsharp=5:5:1.0:5:5:0.0",
                "-frames:v", "300",
                "-q:v", "1",
                frame_pattern
            ]
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
            
            frames = sorted(tmpdir_path.glob("frame_*.jpg"))
            if not frames:
                log.info("No frames extracted from video: %s", path)
                return ""
            
            log.info("Extracted %d frames from video for OCR", len(frames))
            
            all_text = []
            seen_text = set()
            for i, frame_path in enumerate(frames):
                try:
                    img = PIL.Image.open(str(frame_path))
                    
                    tess_text = ""
                    if pytesseract:
                        tess_text = _ocr_tesseract(img)
                    
                    easy_text = ""
                    if easyocr and i % 3 == 0:
                        try:
                            easy_text = _ocr_easyocr(str(frame_path))
                        except Exception:
                            pass
                    
                    frame_text = _merge_ocr_results(tess_text, easy_text).strip()
                    
                    if frame_text:
                        text_key = frame_text[:50].strip().lower()
                        if text_key and text_key not in seen_text:
                            all_text.append(frame_text)
                            seen_text.add(text_key)
                            if i < 3:
                                log.info("OCR frame %d: %s", i+1, frame_text[:100])
                except Exception as frame_e:
                    log.warning("OCR failed for frame %d: %s", i+1, frame_e)
                    continue
            
            result = "\n\n".join(all_text)
            log.info("Video OCR completed: %d unique frames, total text len=%d", len(all_text), len(result))
            
            if llm_client and result and len(result) > 50:
                try:
                    import json
                    try:
                        from knowledge_bot.core.config import load_config
                        cfg = load_config()
                        from knowledge_bot.core.settings import load_prompt
                        ocr_clean_prompt = load_prompt(cfg.agent_config_path, "ocr_clean")
                    except Exception:
                        prompt_path = Path(__file__).parent / "config" / "prompts" / "ocr_clean.txt"
                        if prompt_path.exists():
                            ocr_clean_prompt = prompt_path.read_text(encoding="utf-8")
                        else:
                            ocr_clean_prompt = None
                    
                    if ocr_clean_prompt:
                        user_input = ocr_clean_prompt.replace("{ocr_text}", result)
                        cleaned = llm_client.chat("", user_input).content or result
                        if cleaned and len(cleaned.strip()) > len(result.strip()) * 0.5:
                            log.info("LLM cleaned OCR: %d -> %d chars", len(result), len(cleaned))
                            return cleaned.strip()
                except Exception as llm_err:
                    log.warning("LLM OCR cleanup failed: %s", llm_err)
            
            return result
    except Exception as e:
        log.warning("extract_ocr_from_video failed: %s", e)
        return ""
