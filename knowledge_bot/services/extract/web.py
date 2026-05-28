"""URL and PDF text extraction."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from knowledge_bot.services.extract._deps import pdfminer, requests, trafilatura
from knowledge_bot.services.extract.types import ExtractedBundle

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
