from __future__ import annotations

import json
from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any, Optional, Tuple
import os
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
fwhisper = _safe_import("faster_whisper")
owhisper = _safe_import("whisper")
yt_dlp = _safe_import("yt_dlp")
yt_transcript_api = _safe_import("youtube_transcript_api")
import tempfile
import subprocess
import base64
import shutil

# Глобальный EasyOCR reader (singleton) для переиспользования
_easyocr_reader = None
_easyocr_reader_lock = None

# Глобальная модель faster_whisper (singleton) для переиспользования и экономии памяти
_faster_whisper_model = None
_faster_whisper_model_name = None

def _get_easyocr_reader():
    """Получить или создать глобальный EasyOCR reader (singleton)"""
    global _easyocr_reader, _easyocr_reader_lock
    log = logging.getLogger("kb.extract")
    
    if easyocr is None:
        log.info("EasyOCR module not available")
        return None
    
    if _easyocr_reader is None:
        try:
            log.info("Initializing EasyOCR reader (this may take 30-60 seconds on first run)...")
            _easyocr_reader = easyocr.Reader(['en', 'ru'], gpu=False, verbose=False)
            log.info("EasyOCR reader initialized successfully")
        except Exception as e:
            log.error("Failed to initialize EasyOCR reader: %s", e, exc_info=True)
            _easyocr_reader = False  # Mark as failed to avoid retrying
    
    return _easyocr_reader if _easyocr_reader is not False else None

# Логируем статус импортов OCR движков при загрузке модуля
_log = logging.getLogger("kb.extract")
if pytesseract:
    _log.info("Tesseract OCR: available")
else:
    _log.warning("Tesseract OCR: NOT available (pytesseract not installed)")

if easyocr:
    _log.info("EasyOCR: module imported successfully (reader will be initialized on first use)")
else:
    _log.warning("EasyOCR: NOT available (easyocr not installed)")


class VisionRateLimitError(Exception):
    """OpenRouter Vision 429 после retry (RPM). Остановить reprocess batch."""


@dataclass
class ExtractedBundle:
    raw_text: str = ""
    urls: list[str] = None
    meta: dict[str, Any] = None
    # derived
    url_text: str = ""
    pdf_text: str = ""
    ocr_text: str = ""
    asr_text: str = ""
    vision_text: str = ""  # Vision analysis для изображений/видео
    yt_transcript_text: str = ""  # Транскрипт с YouTube (без загрузки видео)

    def to_summary(self) -> dict[str, Any]:
        derived = {
            "url_text": self.url_text,
            "pdf_text": self.pdf_text,
            "ocr_text": self.ocr_text,
            "asr_text": self.asr_text,
            "vision_text": self.vision_text,
        }
        if self.yt_transcript_text:
            derived["yt_transcript_text"] = self.yt_transcript_text
        return {
            "raw_text": self.raw_text,
            "urls": self.urls or [],
            "meta": self.meta or {},
            "derived": derived,
        }


def simple_from_text(text: str) -> ExtractedBundle:
    log = logging.getLogger("kb.extract")
    urls: list[str] = []
    for m in re.finditer(r"https?://[^\s)]+", text):
        urls.append(m.group(0))
    url_text = ""
    if urls:
        if trafilatura is None:
            log.info("trafilatura not installed; skip URL extract (urls=%d)", len(urls))
        else:
            try:
                fetched = trafilatura.fetch_url(urls[0])
                url_text = trafilatura.extract(fetched) or ""
                log.info("url_text extracted: len=%d from %s", len(url_text or ""), urls[0])
            except Exception as e:
                log.warning("trafilatura failed: %s", e)
        # Fallback: extract page title via requests if no body text
        if not url_text and requests is not None:
            try:
                resp = requests.get(urls[0], headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
                html = resp.text or ""
                # Try og:title first
                m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
                if m:
                    url_text = m.group(1).strip()
                else:
                    # Then <title>
                    m2 = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
                    if m2:
                        url_text = re.sub(r"\s+", " ", m2.group(1)).strip()
                log.info("url_title fallback: %s (len=%d)", "yes" if url_text else "no", len(url_text or ""))
            except Exception as e:
                log.warning("requests title fallback failed: %s", e)
    return ExtractedBundle(raw_text=text, urls=urls, meta={}, url_text=url_text)


def extract_from_url(url: str) -> ExtractedBundle:
    log = logging.getLogger("kb.extract")
    txt = ""
    if trafilatura is not None:
        try:
            fetched = trafilatura.fetch_url(url)
            txt = trafilatura.extract(fetched) or ""
            log.info("extract_from_url: len=%d %s", len(txt or ""), url)
        except Exception as e:
            log.warning("extract_from_url failed: %s", e)
    if not txt and requests is not None:
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            html = resp.text or ""
            m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
            if m:
                txt = m.group(1).strip()
            else:
                m2 = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
                if m2:
                    txt = re.sub(r"\s+", " ", m2.group(1)).strip()
            log.info("extract_from_url title fallback: len=%d %s", len(txt or ""), url)
        except Exception as e:
            log.warning("requests title fallback failed: %s", e)
    return ExtractedBundle(raw_text=url, urls=[url], meta={}, url_text=txt)


def _youtube_video_id(url: str) -> Optional[str]:
    """Извлекает video_id из YouTube URL."""
    u = (url or "").strip()
    if "youtube.com/watch" in u:
        m = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", u)
        return m.group(1) if m else None
    if "youtu.be/" in u:
        m = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", u)
        return m.group(1) if m else None
    if "youtube.com/embed/" in u:
        m = re.search(r"embed/([a-zA-Z0-9_-]{11})", u)
        return m.group(1) if m else None
    if "youtube.com/shorts/" in u:
        m = re.search(r"shorts/([a-zA-Z0-9_-]{11})", u)
        return m.group(1) if m else None
    return None


def get_youtube_video_title(url: str) -> Optional[str]:
    """Получает название ролика через oEmbed (не требует API key). Для ссылок без транскрипта."""
    vid = _youtube_video_id(url)
    if not vid or not requests:
        return None
    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"
        r = requests.get(oembed_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.ok:
            data = r.json()
            title = (data.get("title") or "").strip()
            if title and len(title) < 300:
                return title
    except Exception as e:
        log = logging.getLogger("kb.extract")
        log.debug("oEmbed title for %s failed: %s", vid, e)
    return None


def _parse_subtitle_file(path: Path) -> str:
    """Извлекает текст из SRT/VTT файла (убирает таймкоды)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        # Убираем WEBVTT header, таймкоды (00:00:00.000 --> 00:00:02.500), номера
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
                continue
            if re.match(r"^\d{2}:\d{2}:\d{2}[\.,]\d+", line):  # таймкод
                continue
            if re.match(r"^\d+$", line):  # номер кадра
                continue
            if " --> " in line:  # таймкод range
                continue
            lines.append(line)
        return " ".join(lines)
    except Exception:
        return ""


_YT_PROXY_MISSING = object()

def _fetch_youtube_transcript_ytdlp(url: str, proxy: str | None = _YT_PROXY_MISSING) -> str:
    """Транскрипт через yt-dlp. proxy=None — без прокси (fallback при сбое)."""
    log = logging.getLogger("kb.extract")
    if not yt_dlp:
        return ""
    video_id = _youtube_video_id(url)
    if not video_id:
        return ""
    if proxy is _YT_PROXY_MISSING:
        proxy = os.environ.get("YOUTUBE_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    with tempfile.TemporaryDirectory(prefix="kb_yt_") as tmpdir:
        out_tmpl = str(Path(tmpdir) / "%(id)s")
        opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["ru", "en", "ru.*", "en.*"],
            "subtitlesformat": "srt/vtt/best",
            "outtmpl": out_tmpl,
            "quiet": True,
            "no_warnings": True,
        }
        if proxy:
            opts["proxy"] = proxy
            log.info("YouTube transcript via yt-dlp with proxy for %s", video_id)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            # Ищем субтитры: VIDEO_ID.lang.srt или .vtt
            for sub_path in list(Path(tmpdir).glob("*.srt")) + list(Path(tmpdir).glob("*.vtt")):
                result = _parse_subtitle_file(sub_path)
                if result and len(result) > 20:
                    log.info("YouTube transcript (yt-dlp): %d chars for %s", len(result), video_id)
                    return result
        except Exception as e:
            log.warning("yt-dlp transcript failed for %s: %s", video_id, e)
    return ""


def _fetch_youtube_transcript_api(video_id: str, proxy: str | None) -> str:
    """Транскрипт через youtube-transcript-api (новый API: fetch)."""
    log = logging.getLogger("kb.extract")
    if not yt_transcript_api:
        return ""
    try:
        proxy_config = None
        if proxy:
            try:
                from youtube_transcript_api.proxies import GenericProxyConfig
                proxy_config = GenericProxyConfig(https_url=proxy, http_url=proxy)
            except Exception as pe:
                log.warning("Proxy config failed: %s", pe)
        api = yt_transcript_api.YouTubeTranscriptApi(proxy_config=proxy_config)
        fetched = api.fetch(video_id, languages=("ru", "en"))
        if fetched and len(fetched) > 0:
            result = " ".join(s.text.strip() for s in fetched if getattr(s, "text", "").strip())
            if result:
                log.info("YouTube transcript (api): %d chars for %s", len(result), video_id)
                return result
    except Exception as e:
        log.warning("youtube-transcript-api failed for %s: %s", video_id, e)
    return ""


# Один запрос к YouTube за раз + пауза, чтобы не перегружать socks-proxy
_yt_transcript_lock = None

def _get_yt_lock():
    global _yt_transcript_lock
    if _yt_transcript_lock is None:
        import threading
        _yt_transcript_lock = threading.Lock()
    return _yt_transcript_lock


def fetch_youtube_transcript(url: str) -> str:
    """Получает транскрипт YouTube через YOUTUBE_PROXY. Запросы сериализованы и с паузой,
    чтобы не перегружать socks-proxy."""
    log = logging.getLogger("kb.extract")
    video_id = _youtube_video_id(url)
    if not video_id:
        return ""
    proxy = os.environ.get("YOUTUBE_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

    def _try_both(use_proxy: str | None) -> str:
        result = _fetch_youtube_transcript_api(video_id, use_proxy)
        if result:
            return result
        if yt_dlp:
            result = _fetch_youtube_transcript_ytdlp(url, proxy=use_proxy)
            if result:
                return result
        return ""

    lock = _get_yt_lock()
    with lock:
        # Пауза перед запросом, чтобы не слать пачки подряд (reprocess/бот)
        _pause = os.environ.get("YOUTUBE_TRANSCRIPT_PAUSE_SECONDS", "1")
        try:
            pause_sec = float(_pause)
            if pause_sec > 0:
                import time
                time.sleep(pause_sec)
        except ValueError:
            pass
        result = _try_both(proxy)
        if result:
            return result
        if proxy:
            log.info("YouTube transcript: retry without proxy for %s", video_id)
            result = _try_both(None)
    return result if result else ""


def extract_from_pdf(path: Path) -> str:
    log = logging.getLogger("kb.extract")
    if pdfminer is None:
        log.info("pdfminer not installed; skip PDF extract: %s", path)
        return ""
    try:
        # pdfminer.high_level.extract_text
        txt = pdfminer.high_level.extract_text(str(path)) or ""
        log.info("extract_from_pdf: len=%d %s", len(txt or ""), path)
        return txt
    except Exception as e:
        log.warning("extract_from_pdf failed: %s", e)
        return ""


def _ocr_tesseract(img: PIL.Image.Image) -> str:
    """OCR через Tesseract с улучшенной предобработкой"""
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
        
        # Конвертируем в RGB
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Увеличиваем размер для лучшего распознавания (больше для видео)
        width, height = img.size
        if width < 3000 or height < 3000:
            scale = max(3000 / width, 3000 / height)
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, PIL.Image.LANCZOS)
        
        # Конвертируем в grayscale
        gray = img.convert('L')
        
        # Убираем шум (дешпикл)
        if has_scipy:
            try:
                img_array = np.array(gray)
                # Медианный фильтр для удаления шума
                img_array = ndimage.median_filter(img_array, size=3)
                gray = PIL.Image.fromarray(img_array, mode='L')
            except Exception:
                pass
        
        # Автоматическая коррекция контраста (более агрессивная)
        gray = ImageOps.autocontrast(gray, cutoff=1)
        
        # Улучшаем контраст (более агрессивно)
        enhancer = ImageEnhance.Contrast(gray)
        gray = enhancer.enhance(2.0)
        
        # Улучшаем резкость
        enhancer = ImageEnhance.Sharpness(gray)
        gray = enhancer.enhance(1.5)
        
        # Пробуем разные варианты предобработки
        results = []
        
        # Вариант 1: Адаптивная бинаризация Otsu (если scipy доступен)
        if has_scipy and has_numpy:
            try:
                from skimage.filters import threshold_otsu
                img_array = np.array(gray)
                # Otsu threshold - адаптивная бинаризация
                threshold = threshold_otsu(img_array)
                binary = (img_array > threshold).astype(np.uint8) * 255
                binary_img = PIL.Image.fromarray(binary, mode='L')
                
                for psm in ['6', '7', '11', '3', '12']:
                    try:
                        # Whitelist символов (экранируем фигурные скобки в f-string)
                        whitelist = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя.,!?;:()[]{{}}\\'\"- "
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
                # Если scikit-image недоступен, используем простую бинаризацию
                if has_numpy:
                    try:
                        img_array = np.array(gray)
                        # Otsu-like: используем среднее значение как порог
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
        
        # Вариант 2: Улучшенное grayscale изображение
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
        
        # Выбираем лучший результат (по количеству букв/цифр)
        if results:
            results.sort(reverse=True, key=lambda x: x[0])
            return results[0][1]
        
        return ""
    except Exception as e:
        logging.getLogger("kb.extract").warning("Tesseract OCR failed: %s", e)
        return ""


def _ocr_easyocr(img_path: str) -> str:
    """OCR через EasyOCR с предобработкой изображения"""
    log = logging.getLogger("kb.extract")
    
    reader = _get_easyocr_reader()
    if reader is None:
        return ""
    
    tmp_path_to_cleanup = None
    try:
        # Предобработка изображения для лучшего OCR (как в Tesseract)
        original_img_path = img_path
        if PIL:
            try:
                from PIL import ImageEnhance, ImageOps
                img = PIL.Image.open(img_path)
                
                # Конвертируем в RGB если нужно
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Увеличиваем размер для лучшего распознавания
                width, height = img.size
                if width < 2000 or height < 2000:
                    scale = max(2000 / width, 2000 / height)
                    new_size = (int(width * scale), int(height * scale))
                    img = img.resize(new_size, PIL.Image.LANCZOS)
                    # Сохраняем предобработанное изображение во временный файл
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                        tmp_path_to_cleanup = tmp.name
                        img.save(tmp_path_to_cleanup, 'JPEG', quality=95)
                    img_path = tmp_path_to_cleanup
                    log.debug("Preprocessed image saved to temp file for EasyOCR")
            except Exception as preprocess_err:
                log.debug("Image preprocessing for EasyOCR failed, using original: %s", preprocess_err)
        
        # EasyOCR автоматически определяет язык
        results = reader.readtext(img_path)
        
        # Объединяем результаты с более высоким порогом confidence
        lines = []
        confidences = []
        for (bbox, text, confidence) in results:
            confidences.append(confidence)
            # Снизили порог до 0.4 для лучшего захвата текста (можно настроить)
            if confidence > 0.4:
                text_clean = text.strip()
                # Дополнительная фильтрация: убираем очень короткие строки с мусором
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
        # Удаляем временный файл если был создан
        if tmp_path_to_cleanup and tmp_path_to_cleanup != original_img_path:
            try:
                os.unlink(tmp_path_to_cleanup)
            except Exception:
                pass


def _merge_ocr_results(tesseract_text: str, easyocr_text: str) -> str:
    """
    Объединяет результаты двух OCR движков, убирая только точные дубликаты.
    Использует умную дедупликацию - сохраняет уникальный контент из обоих источников.
    """
    log = logging.getLogger("kb.extract")
    
    if not tesseract_text and not easyocr_text:
        return ""
    
    if not tesseract_text:
        log.info("Merged OCR: Only EasyOCR result (%d chars)", len(easyocr_text))
        return easyocr_text
    if not easyocr_text:
        log.info("Merged OCR: Only Tesseract result (%d chars)", len(tesseract_text))
        return tesseract_text
    
    # Разбиваем на строки и слова для более умного объединения
    tess_lines = [l.strip() for l in tesseract_text.splitlines() if l.strip()]
    easy_lines = [l.strip() for l in easyocr_text.splitlines() if l.strip()]
    
    log.debug("Merging OCR: Tesseract=%d lines, EasyOCR=%d lines", len(tess_lines), len(easy_lines))
    
    # Объединяем, убирая только точные дубликаты (case-insensitive)
    # Приоритет: если обе строки очень похожи (>80% совпадение слов), берем более длинную
    merged = []
    seen_normalized = set()  # Для быстрой проверки точных дубликатов
    
    all_lines = []
    # Сначала добавляем все строки из обоих источников с пометкой источника
    for line in tess_lines:
        all_lines.append(('tess', line))
    for line in easy_lines:
        all_lines.append(('easy', line))
    
    for source, line in all_lines:
        line_normalized = line.lower().strip()
        
        # Пропускаем пустые строки
        if not line_normalized:
            continue
        
        # Проверяем точные дубликаты (case-insensitive)
        if line_normalized in seen_normalized:
            continue
        
        # Проверяем похожие строки (более 80% слов совпадают) - берем более длинную
        is_similar = False
        line_words = set(line_normalized.split())
        
        for existing_line in merged:
            existing_words = set(existing_line.lower().split())
            if len(line_words) == 0 or len(existing_words) == 0:
                continue
            
            # Вычисляем пересечение слов
            intersection = line_words & existing_words
            union = line_words | existing_words
            
            if len(union) > 0:
                similarity = len(intersection) / len(union)
                # Если похожесть >80% и текущая строка длиннее - заменяем
                if similarity > 0.8 and len(line) > len(existing_line):
                    log.debug("Replacing similar line (similarity=%.2f): '%s' -> '%s'", 
                             similarity, existing_line[:50], line[:50])
                    merged.remove(existing_line)
                    # Удаляем normalized версию старой строки
                    seen_normalized.discard(existing_line.lower().strip())
                    break
                elif similarity > 0.8:
                    # Похожая строка уже есть и она не короче - пропускаем текущую
                    is_similar = True
                    break
        
        if not is_similar:
            merged.append(line)
            seen_normalized.add(line_normalized)
    
    result = '\n'.join(merged)
    log.info("Merged OCR: Tesseract=%d chars (%d lines), EasyOCR=%d chars (%d lines), Merged=%d chars (%d unique lines)", 
             len(tesseract_text), len(tess_lines), len(easyocr_text), len(easy_lines), len(result), len(merged))
    return result


# --- Vision (OpenRouter, мультимодель из VISION_MODEL) для видео ---
def _load_vision_prompt() -> str:
    try:
        from knowledge_bot.core.config import load_config
        cfg = load_config()
        from knowledge_bot.core.settings import load_prompt
        return load_prompt(cfg.agent_config_path, "vision").strip()
    except Exception:
        p = Path(__file__).resolve().parent / "config" / "prompts" / "vision.txt"
        return p.read_text(encoding="utf-8").strip() if p.exists() else "Опиши сцену из кадров видео (2-5 предложений). Ответ на русском."


def _extract_video_middle_frame(video_path: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """Извлекает один кадр из середины видео. Возвращает (frame_path, tmpdir) или (None, None)."""
    dur = _get_video_duration(video_path)
    t = dur / 2 if dur > 0 else 0
    tmpdir = Path(tempfile.mkdtemp(prefix="kb_video_ocr_"))
    out = tmpdir / "frame_mid.jpg"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(t), "-i", str(video_path), "-vframes", "1", "-q:v", "2", str(out)],
            capture_output=True,
            check=True,
            timeout=15,
        )
        if out.exists() and out.stat().st_size > 0:
            return out, tmpdir
    except Exception:
        pass
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass
    return None, None


def _get_video_duration(video_path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return float(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else 0
    except Exception:
        return 0


def _extract_video_frames(video_path: Path, n: int = 5) -> Tuple[list[Path], Path]:
    """Извлекает n кадров равномерно по длине видео. Возвращает (frames, tmpdir)."""
    dur = _get_video_duration(video_path)
    ts = [0] if dur <= 0 else [dur * i / max(n - 1, 1) for i in range(n)]
    tmpdir = Path(tempfile.mkdtemp(prefix="kb_video_"))
    frames = []
    for i, t in enumerate(ts):
        out = tmpdir / f"frame_{i:02d}.jpg"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(t), "-i", str(video_path), "-vframes", "1", "-q:v", "2", str(out)],
                capture_output=True,
                check=True,
                timeout=15,
            )
            if out.exists() and out.stat().st_size > 0:
                frames.append(out)
        except subprocess.CalledProcessError:
            if not frames:
                try:
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", str(video_path), "-vframes", "1", "-q:v", "2", str(out)],
                        capture_output=True,
                        check=True,
                        timeout=15,
                    )
                    if out.exists() and out.stat().st_size > 0:
                        frames.append(out)
                except Exception:
                    pass
            break
        except Exception:
            break
    return frames, tmpdir


def _llm_asr_sufficient_to_skip_vision(llm_client: Optional[Any], asr_text: str) -> bool:
    """
    Один короткий JSON-запрос к основному LLM: достаточен ли транскрипт, чтобы не вызывать Vision.
    При отсутствии клиента или ошибке — False (Vision выполняем).
    """
    log = logging.getLogger("kb.extract")
    if not llm_client:
        return False
    t = (asr_text or "").strip()
    if len(t) < 25:
        return False
    try:
        from knowledge_bot.core.config import load_config
        from knowledge_bot.core.settings import load_prompt

        cfg = load_config()
        system = load_prompt(cfg.agent_config_path, "asr_skip_vision_gate")
        user = json.dumps({"transcript": t[:4500]}, ensure_ascii=False)
        model = os.environ.get("VISION_ASR_GATE_MODEL", "deepseek-chat")
        result = llm_client.chat_json(system, user, model=model, timeout=35.0, max_tokens=96)
        payload = result.content if isinstance(result.content, dict) else {}
        val = payload.get("sufficient")
        if isinstance(val, bool):
            log.info("ASR vision gate: sufficient=%s", val)
            return val
        log.warning("ASR vision gate: unexpected JSON, running Vision")
        return False
    except Exception as e:
        log.warning("ASR vision gate failed: %s — running Vision", e)
        return False


def extract_vision_from_video(path: Path, asr_text: str = "", llm_client: Optional[Any] = None) -> str:
    """Vision-анализ видео: извлекает кадры, отправляет в OpenRouter (см. VISION_MODEL)."""
    log = logging.getLogger("kb.extract")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or not requests:
        log.info("Vision skip: OPENROUTER_API_KEY or requests not available")
        return ""
    # Экономия лимита: один LLM-запрос — достаточен ли ASR без описания кадров
    if (
        os.environ.get("VISION_SKIP_IF_ASR_GOOD", "1") == "1"
        and asr_text
        and _llm_asr_sufficient_to_skip_vision(llm_client, asr_text)
    ):
        log.info("Vision skip: LLM says ASR sufficient (%d chars)", len(asr_text))
        return ""
    # Было: allenai/molmo-2-8b:free — условия у провайдера менялись; дефолт — Gemini Flash на OpenRouter.
    model = os.environ.get("VISION_MODEL") or os.environ.get("VISION_FALLBACK_MODEL", "google/gemini-2.0-flash-001")
    base_url = "https://openrouter.ai/api/v1"
    frames = []
    tmpdir = None
    try:
        frames, tmpdir = _extract_video_frames(path, n=5)
        if not frames:
            log.info("Vision: no frames extracted from %s", path.name)
            return ""
        images_b64 = [base64.b64encode(f.read_bytes()).decode("ascii") for f in frames]
        content = [{"type": "text", "text": _load_vision_prompt()}]
        for b64 in images_b64:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 500,
            "temperature": 0.2,
        }
        from knowledge_bot.services.openrouter_rate_limit import openrouter_post

        try:
            r = openrouter_post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/knowledge-bot",
                },
                json_payload=payload,
                timeout=90.0,
            )
            if r.ok:
                text = (r.json() or {}).get("choices", [{}])[0].get("message", {}).get("content", "")
                log.info("Vision: %d chars from %d frames (%s) for %s", len(text or ""), len(frames), model, path.name)
                return (text or "").strip()
            from knowledge_bot.services.api_billing_alerts import send_billing_alert_if_needed

            send_billing_alert_if_needed("OpenRouter (Vision)", r.status_code, r.text or "")
            if r.status_code == 429:
                log.warning("Vision API 429 (rate limit после retry) — останавливаем batch")
                raise VisionRateLimitError("OpenRouter Vision rate limit (429)")
            log.warning("Vision API %s: %s", r.status_code, (r.text or "")[:200])
            return ""
        except VisionRateLimitError:
            raise
        except Exception as e:
            log.warning("Vision failed: %s", e)
            return ""
    except Exception as e:
        log.warning("Vision extract failed: %s", e)
        return ""
    finally:
        if tmpdir and tmpdir.exists():
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass


def extract_from_image(path: Path, llm_client: Optional[Any] = None) -> str:
    """Извлекает текст из изображения используя ДВА OCR движка (Tesseract + EasyOCR)"""
    log = logging.getLogger("kb.extract")
    if PIL is None:
        log.info("Pillow not installed; skip OCR: %s", path)
        return ""
    
    if pytesseract is None and easyocr is None:
        log.info("No OCR engines available; skip OCR: %s", path)
        return ""
    
    try:
        img = PIL.Image.open(str(path))
        
        # Запускаем оба OCR параллельно
        tesseract_text = ""
        easyocr_text = ""
        
        if pytesseract:
            tesseract_text = _ocr_tesseract(img)
            log.info("Tesseract OCR: %d chars", len(tesseract_text))
        
        if easyocr:
            log.info("Starting EasyOCR for image...")
            easyocr_text = _ocr_easyocr(str(path))
            if easyocr_text:
                log.info("EasyOCR completed: %d chars", len(easyocr_text))
            else:
                log.warning("EasyOCR returned empty result")
        
        # Объединяем результаты
        merged = _merge_ocr_results(tesseract_text, easyocr_text)
        
        # Без эвристик - используем результат как есть
        result = merged
        log.info("extract_from_image: final len=%d (Tesseract+EasyOCR merged) %s", len(result or ""), path)
        
        # Опциональная очистка через LLM
        if llm_client and result and len(result) > 50:
            try:
                import json
                # Пробуем загрузить промпт через config
                try:
                    from knowledge_bot.core.config import load_config
                    cfg = load_config()
                    from knowledge_bot.core.settings import load_prompt
                    ocr_clean_prompt = load_prompt(cfg.agent_config_path, "ocr_clean")
                except Exception:
                    # Fallback: пробуем прямой путь
                    prompt_path = Path(__file__).parent / "config" / "prompts" / "ocr_clean.txt"
                    if prompt_path.exists():
                        ocr_clean_prompt = prompt_path.read_text(encoding="utf-8")
                    else:
                        ocr_clean_prompt = None
                
                if ocr_clean_prompt:
                    # Заменяем плейсхолдер в промпте
                    user_input = ocr_clean_prompt.replace("{ocr_text}", result)
                    cleaned = llm_client.chat("", user_input).content or result
                    cleaned_strip = cleaned.strip()
                    # LLM отверг контент как шум — не подставляем
                    if "текст отсутствует" in cleaned_strip.lower() or "[текст отсутствует]" in cleaned_strip.lower():
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
    """
    Извлекает текст из видео через OCR кадров.
    НЕ покадрово - извлекает кадры с интервалом (по умолчанию каждые 3 секунды).
    
    Args:
        path: Путь к видео файлу
        frame_interval: Интервал между кадрами в секундах (по умолчанию 3.0)
    
    Returns:
        Объединенный текст из всех кадров
    """
    log = logging.getLogger("kb.extract")
    if PIL is None:
        log.info("Pillow not installed; skip video OCR: %s", path)
        return ""
    
    if pytesseract is None and easyocr is None:
        log.info("No OCR engines available; skip video OCR: %s", path)
        return ""
    
    try:
        import tempfile
        # Извлекаем кадры с интервалом используя ffmpeg
        # -vf fps=1/3 означает 1 кадр в 3 секунды (можно настроить через frame_interval)
        fps = 1.0 / frame_interval
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            # Извлекаем кадры в временную директорию
            frame_pattern = str(tmpdir_path / "frame_%04d.jpg")
            # Улучшаем качество кадров для лучшего OCR
            # Увеличиваем разрешение и используем максимальное качество JPEG
            cmd = [
                "ffmpeg", "-y", "-i", str(path),
                "-vf", f"fps={fps:.3f},scale=3000:-1,unsharp=5:5:1.0:5:5:0.0",  # Увеличиваем до 3000px + unsharp mask для резкости
                "-frames:v", "300",  # До 300 кадров (для видео до 5 минут при 1 fps)
                "-q:v", "1",  # Максимальное качество JPEG (1 = лучшее)
                frame_pattern
            ]
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False  # Не падаем если команда не удалась
            )
            
            # Собираем все извлеченные кадры
            frames = sorted(tmpdir_path.glob("frame_*.jpg"))
            if not frames:
                log.info("No frames extracted from video: %s", path)
                return ""
            
            log.info("Extracted %d frames from video for OCR", len(frames))
            
            # Применяем OCR к каждому кадру
            all_text = []
            seen_text = set()  # Дедупликация похожих строк
            for i, frame_path in enumerate(frames):
                try:
                    img = PIL.Image.open(str(frame_path))
                    
                    # Используем Tesseract для всех кадров
                    tess_text = ""
                    if pytesseract:
                        tess_text = _ocr_tesseract(img)
                    
                    # EasyOCR пробуем только для каждого 3-го кадра (чтобы не было слишком медленно)
                    easy_text = ""
                    if easyocr and i % 3 == 0:
                        try:
                            easy_text = _ocr_easyocr(str(frame_path))
                        except Exception:
                            pass
                    
                    # Объединяем результаты
                    frame_text = _merge_ocr_results(tess_text, easy_text).strip()
                    
                    if frame_text:
                        # Простая дедупликация: используем первые 50 символов для сравнения
                        text_key = frame_text[:50].strip().lower()
                        if text_key and text_key not in seen_text:
                            all_text.append(frame_text)
                            seen_text.add(text_key)
                            if i < 3:  # Логируем первые 3 кадра
                                log.info("OCR frame %d: %s", i+1, frame_text[:100])
                except Exception as frame_e:
                    log.warning("OCR failed for frame %d: %s", i+1, frame_e)
                    continue
            
            result = "\n\n".join(all_text)
            log.info("Video OCR completed: %d unique frames, total text len=%d", len(all_text), len(result))
            
            # Опциональная очистка через LLM
            if llm_client and result and len(result) > 50:
                try:
                    import json
                    # Пробуем загрузить промпт через config
                    try:
                        from knowledge_bot.core.config import load_config
                        cfg = load_config()
                        from knowledge_bot.core.settings import load_prompt
                        ocr_clean_prompt = load_prompt(cfg.agent_config_path, "ocr_clean")
                    except Exception:
                        # Fallback: пробуем прямой путь
                        prompt_path = Path(__file__).parent / "config" / "prompts" / "ocr_clean.txt"
                        if prompt_path.exists():
                            ocr_clean_prompt = prompt_path.read_text(encoding="utf-8")
                        else:
                            ocr_clean_prompt = None
                    
                    if ocr_clean_prompt:
                        # Заменяем плейсхолдер в промпте
                        user_input = ocr_clean_prompt.replace("{ocr_text}", result)
                        cleaned = llm_client.chat("", user_input).content or result
                        if cleaned and len(cleaned.strip()) > len(result.strip()) * 0.5:  # Если результат не слишком короткий
                            log.info("LLM cleaned OCR: %d -> %d chars", len(result), len(cleaned))
                            return cleaned.strip()
                except Exception as llm_err:
                    log.warning("LLM OCR cleanup failed: %s", llm_err)
            
            return result
    except Exception as e:
        log.warning("extract_ocr_from_video failed: %s", e)
        return ""


def extract_from_path(path_str: str, note_text: Optional[str] = None, llm_client: Optional[Any] = None) -> ExtractedBundle:
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
        # Изображения: только OCR (vision analysis отключен)
        log = logging.getLogger("kb.extract")
        ocr_text = extract_from_image(path, llm_client=llm_client)
        log.info("OCR for image: %d chars", len(ocr_text or ""))
        
        return ExtractedBundle(
            raw_text=raw, 
            urls=[], 
            meta={"file": str(path)}, 
            ocr_text=ocr_text,
            vision_text=None  # Vision analysis отключен
        )
    
    if suffix in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
        # Видео: ASR + OCR среднего кадра + Vision (семантика кадров)
        log = logging.getLogger("kb.extract")
        
        # ASR для видео с звуком
        log.info("Starting ASR for video: %s", path.name)
        asr_text = transcribe_av(path)
        log.info("ASR completed: %d chars", len(asr_text or ""))
        
        # OCR среднего кадра — покрывает видео из одной надписи (мемы, цитаты)
        ocr_text = ""
        mid_frame, ocr_tmpdir = _extract_video_middle_frame(path)
        if mid_frame and (pytesseract or easyocr):
            try:
                ocr_text = extract_from_image(mid_frame, llm_client=llm_client) or ""
                if ocr_text:
                    log.info("Video OCR (middle frame): %d chars", len(ocr_text))
            finally:
                if ocr_tmpdir and ocr_tmpdir.exists():
                    try:
                        shutil.rmtree(ocr_tmpdir, ignore_errors=True)
                    except Exception:
                        pass
        
        # Vision: описание сцены (пропускаем если ASR содержательный — экономия лимита)
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
        # Только аудио - только ASR
        asr_text = transcribe_av(path)
        return ExtractedBundle(raw_text=raw, urls=[], meta={"file": str(path)}, asr_text=asr_text)
    
    # other types → just reference path
    return ExtractedBundle(raw_text=raw, urls=[], meta={"file": str(path)})


def _ffmpeg_extract_wav(src: Path) -> Optional[Path]:
    log = logging.getLogger("kb.extract")
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)
        cmd = ["ffmpeg", "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(wav_path)]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return wav_path
    except Exception as e:
        log.warning("ffmpeg failed: %s", e)
        return None


def transcribe_av(path: Path, model_name: Optional[str] = None) -> str:
    log = logging.getLogger("kb.extract")
    # Default "tiny" to avoid OOM on low-memory servers; set ASR_MODEL=small for better quality if RAM allows
    model_name = model_name or os.environ.get("ASR_MODEL", "tiny")
    asr_lang_env = os.environ.get("ASR_LANGUAGE", "auto").strip()
    # Accept: "auto" or comma-separated preference list like "ru,en"
    prefs = [p.strip() for p in asr_lang_env.split(",") if p.strip()] or ["auto"]
    log.info("ASR start: model=%s lang_pref=%s file=%s", model_name, ",".join(prefs), path)
    # Try HTTP ASR via OpenAI-compatible endpoint (skip for Ollama which lacks /v1/audio/transcriptions)
    if requests is not None:
        try:
            base_url = (
                os.environ.get("ASR_BASE_URL")
                or os.environ.get("OLLAMA_BASE_URL")
                or os.environ.get("OPENAI_BASE_URL")
                or os.environ.get("EMBED_ENDPOINT")
            )
            api_key = os.environ.get("OLLAMA_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ASR_API_KEY")
            endpoint_path = os.environ.get("ASR_ENDPOINT", "/v1/audio/transcriptions")
            is_ollama_base = bool(base_url) and ("11434" in base_url or "ollama" in base_url.lower())
            if base_url and api_key and not is_ollama_base:
                url = base_url.rstrip("/") + endpoint_path
                headers = {"Authorization": f"Bearer {api_key}"}
                files = {
                    "file": (path.name, open(path, "rb"), "application/octet-stream"),
                }
                # choose first non-auto language pref if provided
                first_lang = next((p for p in prefs if p != "auto"), None)
                data = {"model": model_name, "response_format": "json"}
                if first_lang:
                    data["language"] = first_lang
                log.info("ASR http: url=%s model=%s", url, model_name)
                resp = requests.post(url, headers=headers, data=data, files=files, timeout=600)
                if resp.status_code == 200:
                    j = resp.json()
                    text = (j.get("text") if isinstance(j, dict) else "") or ""
                    log.info("ASR done (http): len=%d provider=%s", len(text), base_url)
                    if text:
                        try:
                            log.info("ASR(http) text: %s", (text or "").strip()[:500])
                        except Exception:
                            pass
                        return text
                else:
                    log.warning("ASR http failed: %s %s", resp.status_code, resp.text[:200])
            elif is_ollama_base:
                logging.getLogger("kb.extract").info("ASR http skipped: Ollama base detected (%s)", base_url)
        except Exception as e:
            log.warning("ASR http exception: %s", e)
    # Prefer OpenAI Whisper if installed (CPU ok, small model)
    if owhisper is not None:
        try:
            # convert to wav for stability
            wav = _ffmpeg_extract_wav(path) or path
            model = owhisper.load_model(model_name)
            for lang in prefs:
                lang_arg = None if lang == "auto" else lang
                result = model.transcribe(str(wav), language=lang_arg, task="transcribe")
                text = (result or {}).get("text", "")
                log.info("ASR(whisper) try lang=%s → len=%d", lang, len(text or ""))
                if text:
                    try:
                        log.info("ASR(whisper) text: %s", (text or "").strip()[:500])
                    except Exception:
                        pass
                    return text
        except Exception as e:
            log.warning("whisper failed: %s", e)
    # Fallback to faster-whisper
    if fwhisper is not None:
        try:
            # Используем singleton модель для экономии памяти
            global _faster_whisper_model, _faster_whisper_model_name
            if _faster_whisper_model is None or _faster_whisper_model_name != model_name:
                if _faster_whisper_model is not None:
                    # Освобождаем старую модель перед загрузкой новой
                    del _faster_whisper_model
                    import gc
                    gc.collect()
                log.info("Loading faster_whisper model: %s (this may take time on first run)", model_name)
                _faster_whisper_model = fwhisper.WhisperModel(model_name, compute_type="int8")
                _faster_whisper_model_name = model_name
                log.info("faster_whisper model loaded successfully")
            model = _faster_whisper_model
            # Принудительно пробуем русский и английский (не полагаемся на автоопределение)
            # Если в prefs есть конкретные языки - используем их, иначе ru и en
            if "auto" in prefs or not prefs:
                langs_to_try = ["ru", "en"]
            else:
                langs_to_try = [l for l in prefs if l != "auto"] or ["ru", "en"]
            
            for lang in langs_to_try:
                # Сначала пробуем БЕЗ VAD (VAD часто удаляет весь звук)
                for vad in (False, True):
                    segments, info = model.transcribe(
                        str(path),
                        language=lang,
                        task="transcribe",
                        vad_filter=vad,
                        vad_parameters=dict(min_silence_duration_ms=500) if vad else None,  # Менее агрессивный VAD
                    )
                    text = " ".join(seg.text.strip() for seg in segments if getattr(seg, "text", "").strip())
                    det_lang = getattr(info, "language", None)
                    det_prob = getattr(info, "language_probability", None)
                    log.info("ASR(fw) try lang=%s vad=%s → len=%d detected=%s p=%.2f", lang, vad, len(text or ""), det_lang, det_prob or -1)
                    if text and len(text.strip()) > 10:  # Минимум 10 символов
                        try:
                            log.info("ASR(fw) text: %s", (text or "").strip()[:500])
                        except Exception:
                            pass
                        # Очищаем память после обработки
                        import gc
                        gc.collect()
                        return text
        except Exception as e:
            log.warning("faster_whisper failed: %s", e)
    # Очищаем память даже если ASR не удался
    import gc
    gc.collect()
    log.info("ASR unavailable; returning empty for %s", path)
    return ""


# Best-effort media downloader for supported URLs (YouTube, etc.)
def download_via_ytdlp(url: str, export_root: Path) -> Optional[Path]:
    log = logging.getLogger("kb.extract")
    if yt_dlp is None:
        log.info("yt_dlp not installed; skip media download for %s", url)
        return None
    try:
        from datetime import date
        y = str(date.today().year)
        m = f"{date.today().month:02d}"
        out_dir = export_root / y / m
        out_dir.mkdir(parents=True, exist_ok=True)
        outtmpl = str(out_dir / "%(id)s.%(ext)s")
        ydl_opts = {
            "outtmpl": outtmpl,
            "noprogress": True,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
            "format": os.environ.get("YTDLP_FORMAT", "mp4/bestaudio/best"),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Resolve final filename
            if info is None:
                return None
            if "requested_downloads" in info and info["requested_downloads"]:
                filename = info["requested_downloads"][0].get("filepath")
            else:
                filename = ydl.prepare_filename(info)
        path = Path(filename)
        log.info("yt_dlp downloaded: %s (%s)", path, url)
        return path if path.exists() else None
    except Exception as e:
        log.warning("yt_dlp failed for %s: %s", url, e)
        return None

