"""Dense note index for knowledge preselect (OpenRouter embeddings).

Cache lives in knowledge_bot/data/ (gitignored, not rsynced). Mac and VPS each
build from their own vault. Queries use an in-memory matrix; only new/changed
notes are embedded. A first empty cache builds in the background and catalog
preselect covers the gap.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger("kb.query.dense")

_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "index": None,
    "building": False,
}
_QUERY_CACHE: OrderedDict[str, np.ndarray] = OrderedDict()


def cache_path() -> Path:
    from knowledge_bot.services.query.index_builder import index_json_path

    return index_json_path().parent / "dense_index.npz"


def _cfg_int(key: str, env: str, default: int) -> int:
    from shared.agent.platform_config import platform_int

    return platform_int("knowledge_query", key, env=env, default=default)


def _cfg_str(key: str, env: str, default: str) -> str:
    from shared.agent.platform_config import platform_str

    return platform_str("knowledge_query", key, env=env, default=default)


def _embed_model() -> str:
    from shared.agent.config import load_models_config

    roles = load_models_config().get("roles") or {}
    block = roles.get("embed") if isinstance(roles.get("embed"), dict) else {}
    yaml_model = str((block or {}).get("model") or "").strip()
    return (
        os.environ.get("KNOWLEDGE_EMBED_MODEL")
        or yaml_model
        or _cfg_str("embed_model", "KNOWLEDGE_EMBED_MODEL", "openai/text-embedding-3-large")
    )


def _embed_timeout_sec() -> float:
    from shared.llm_defaults import role_timeout_sec

    return float(role_timeout_sec("embed"))


def _noise_lines() -> set[str]:
    from shared.agent.platform_config import platform_str_list

    raw = platform_str_list("knowledge_query", "embed_noise_lines", default=[])
    return {s.casefold() for s in raw}


def _preview_chars() -> int:
    return _cfg_int("embed_preview_chars", "KNOWLEDGE_EMBED_PREVIEW_CHARS", 1800)


def _batch_size() -> int:
    return max(1, _cfg_int("embed_batch_size", "KNOWLEDGE_EMBED_BATCH_SIZE", 32))


def _sync_max_notes() -> int:
    return _cfg_int("embed_sync_max_notes", "KNOWLEDGE_EMBED_SYNC_MAX_NOTES", 48)


def _query_cache_size() -> int:
    return _cfg_int("embed_query_cache_size", "KNOWLEDGE_EMBED_QUERY_CACHE_SIZE", 64)


def clean_preview(text: str, *, noise: set[str], max_chars: int) -> str:
    kept: list[str] = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.casefold() in noise:
            continue
        kept.append(s)
    out = "\n".join(kept)
    if max_chars > 0 and len(out) > max_chars:
        return out[:max_chars]
    return out


def passage_text(entry: dict[str, Any], *, max_chars: int | None = None) -> str:
    noise = _noise_lines()
    cap = int(max_chars if max_chars is not None else _preview_chars())
    tags = entry.get("tags") or []
    if isinstance(tags, list):
        tag_s = " ".join(str(t) for t in tags if t)
    else:
        tag_s = str(tags)
    parts = [
        f"title: {str(entry.get('title') or '').strip()}",
        f"type: {str(entry.get('type') or '').strip()}",
        f"tags: {tag_s}" if tag_s else "",
        f"city: {str(entry.get('city') or '').strip()}",
        f"category: {str(entry.get('category') or '').strip()}",
        f"address: {str(entry.get('address') or '').strip()}",
        str(entry.get("summary") or "").strip(),
        clean_preview(str(entry.get("preview") or ""), noise=noise, max_chars=cap),
    ]
    return "\n".join(p for p in parts if p and not p.endswith(": "))


def passage_hash(entry: dict[str, Any], *, model: str) -> str:
    blob = f"{model}\n{passage_text(entry)}"
    return hashlib.sha256(blob.encode("utf-8", errors="replace")).hexdigest()[:20]


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return (matrix / norms).astype(np.float32)


def embed_texts(texts: list[str]) -> np.ndarray | None:
    """OpenRouter embeddings. None if the key is missing or the call fails."""
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        log.info("dense embed skipped: OPENROUTER_API_KEY missing")
        return None
    from shared.constants import openrouter_base_url

    model = _embed_model()
    url = f"{openrouter_base_url()}/embeddings"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/knowledge-bot",
        "X-Title": "obsidian-agent",
    }
    timeout = _embed_timeout_sec()
    batch_n = _batch_size()
    rows: list[list[float]] = []
    import requests

    session = requests.Session()
    session.trust_env = False
    n_batches = (len(texts) + batch_n - 1) // batch_n
    for i, start in enumerate(range(0, len(texts), batch_n), start=1):
        batch = texts[start : start + batch_n]
        parsed = _post_embed_batch(session, url, headers, model, batch, timeout)
        if parsed is None:
            log.warning("dense embed failed at batch %d/%d", i, n_batches)
            return None
        rows.extend(parsed)
        if i == 1 or i == n_batches or i % 10 == 0:
            log.info("dense embed batch %d/%d model=%s", i, n_batches, model)
    arr = np.asarray(rows, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[0] != len(texts):
        return None
    return _l2_normalize(arr)


def _post_embed_batch(
    session: Any,
    url: str,
    headers: dict[str, str],
    model: str,
    batch: list[str],
    timeout: float,
) -> list[list[float]] | None:
    import requests

    payload = {"model": model, "input": batch}
    for attempt in range(4):
        try:
            r = session.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException:
            log.warning("dense embed network error attempt=%d", attempt + 1)
            time.sleep(min(8.0, 2.0 ** attempt))
            continue
        if r.status_code in {429, 503}:
            wait = min(30.0, 2.0 ** attempt)
            retry_after = r.headers.get("Retry-After")
            if retry_after:
                try:
                    wait = max(wait, float(retry_after))
                except ValueError:
                    pass
            log.warning("dense embed HTTP %s, sleep %.1fs", r.status_code, wait)
            time.sleep(wait)
            continue
        if r.status_code >= 400:
            log.warning("dense embed HTTP %s body=%s", r.status_code, (r.text or "")[:180])
            return None
        try:
            data = r.json()
        except ValueError:
            return None
        return _parse_embed_response(data, expected=len(batch))
    return None


def _parse_embed_response(data: Any, *, expected: int) -> list[list[float]] | None:
    if not isinstance(data, dict):
        return None
    rows = data.get("data")
    if not isinstance(rows, list) or not rows:
        return None
    ordered = sorted(
        (row for row in rows if isinstance(row, dict)),
        key=lambda row: int(row.get("index") or 0),
    )
    out: list[list[float]] = []
    for row in ordered:
        vec = row.get("embedding")
        if isinstance(vec, list):
            out.append([float(x) for x in vec])
    return out if len(out) == expected else None


class DenseIndex:
    def __init__(
        self,
        paths: list[str],
        hashes: list[str],
        matrix: np.ndarray,
        *,
        model: str,
    ):
        self.paths = list(paths)
        self.hashes = list(hashes)
        self.matrix = matrix.astype(np.float32)
        self.model = model

    @property
    def available(self) -> bool:
        return (
            self.matrix.ndim == 2
            and self.matrix.shape[0] == len(self.paths)
            and self.matrix.shape[0] > 0
        )

    def search(self, question: str, *, top_n: int) -> list[str]:
        if not self.available:
            return []
        q = _embed_query(question)
        if q is None:
            return []
        scores = self.matrix @ q
        n = max(1, min(int(top_n), len(self.paths)))
        idx = np.argpartition(-scores, n - 1)[:n]
        idx = idx[np.argsort(-scores[idx])]
        return [self.paths[int(i)] for i in idx]


def _embed_query(question: str) -> np.ndarray | None:
    key = question.strip()
    if not key:
        return None
    cap = _query_cache_size()
    with _LOCK:
        cached = _QUERY_CACHE.get(key)
        if cached is not None:
            _QUERY_CACHE.move_to_end(key)
            return cached
    vecs = embed_texts([key])
    if vecs is None or vecs.shape[0] != 1:
        return None
    row = vecs[0]
    if cap > 0:
        with _LOCK:
            _QUERY_CACHE[key] = row
            _QUERY_CACHE.move_to_end(key)
            while len(_QUERY_CACHE) > cap:
                _QUERY_CACHE.popitem(last=False)
    return row


def _load_cache(path: Path, *, model: str) -> DenseIndex | None:
    if not path.is_file():
        return None
    try:
        # Never allow_pickle — cache is local but still untrusted if vault is shared.
        payload = np.load(path, allow_pickle=False)
        cached_model = str(payload["model"][0]) if "model" in payload.files else ""
        if cached_model != model:
            log.info("dense cache model mismatch (%s != %s)", cached_model, model)
            return None
        paths = [str(x) for x in payload["paths"].tolist()]
        hashes = [str(x) for x in payload["hashes"].tolist()]
        matrix = payload["matrix"].astype(np.float32)
        if len(paths) != len(hashes) or matrix.shape[0] != len(paths):
            return None
        return DenseIndex(paths, hashes, matrix, model=model)
    except Exception:
        log.warning("dense cache unreadable, rebuilding", exc_info=True)
        return None


def _save_cache(index: DenseIndex, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".npz.tmp")
    # Unicode arrays — no pickle required on load
    max_path = max((len(p) for p in index.paths), default=1)
    max_hash = max((len(h) for h in index.hashes), default=1)
    np.savez(
        tmp,
        matrix=index.matrix,
        paths=np.array(index.paths, dtype=f"U{max_path}"),
        hashes=np.array(index.hashes, dtype=f"U{max_hash}"),
        model=np.array([index.model], dtype=f"U{max(len(index.model), 1)}"),
    )
    tmp.replace(path)


def _plan_sync(
    entries: list[dict[str, Any]],
    current: DenseIndex | None,
    *,
    model: str,
) -> tuple[list[str], list[str], list[np.ndarray], list[dict[str, Any]]]:
    by_hash = {}
    if current is not None:
        for path, h, row in zip(current.paths, current.hashes, current.matrix):
            by_hash[(path, h)] = row
    keep_paths: list[str] = []
    keep_hashes: list[str] = []
    keep_rows: list[np.ndarray] = []
    pending: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        path = str(entry.get("rel_path") or "")
        if not path or path in seen:
            continue
        seen.add(path)
        h = passage_hash(entry, model=model)
        row = by_hash.get((path, h))
        if row is not None:
            keep_paths.append(path)
            keep_hashes.append(h)
            keep_rows.append(row)
        else:
            pending.append(entry)
    return keep_paths, keep_hashes, keep_rows, pending


def _merge(
    keep_paths: list[str],
    keep_hashes: list[str],
    keep_rows: list[np.ndarray],
    new_entries: list[dict[str, Any]],
    new_matrix: np.ndarray,
    *,
    model: str,
) -> DenseIndex:
    paths = list(keep_paths)
    hashes = list(keep_hashes)
    rows = list(keep_rows)
    for i, entry in enumerate(new_entries):
        paths.append(str(entry.get("rel_path") or ""))
        hashes.append(passage_hash(entry, model=model))
        rows.append(new_matrix[i])
    if not rows:
        return DenseIndex([], [], np.zeros((0, 0), dtype=np.float32), model=model)
    matrix = np.stack(rows, axis=0).astype(np.float32)
    return DenseIndex(paths, hashes, matrix, model=model)


def _apply_pending(current: DenseIndex | None, entries: list[dict[str, Any]]) -> DenseIndex | None:
    model = _embed_model()
    keep_paths, keep_hashes, keep_rows, pending = _plan_sync(entries, current, model=model)
    if not pending:
        if current is None:
            return DenseIndex(keep_paths, keep_hashes, np.zeros((0, 0), dtype=np.float32), model=model)
        return DenseIndex(
            keep_paths,
            keep_hashes,
            np.stack(keep_rows, axis=0) if keep_rows else np.zeros((0, 0), dtype=np.float32),
            model=model,
        )
    texts = [passage_text(e) for e in pending]
    log.info("dense sync embedding %d notes (keep=%d)", len(pending), len(keep_paths))
    t0 = time.time()
    matrix = embed_texts(texts)
    if matrix is None:
        return current
    merged = _merge(keep_paths, keep_hashes, keep_rows, pending, matrix, model=model)
    try:
        _save_cache(merged, cache_path())
    except OSError:
        log.warning("dense cache write failed", exc_info=True)
    log.info("dense sync done n=%d in %.1fs", len(merged.paths), time.time() - t0)
    return merged


def clear_dense_cache() -> None:
    with _LOCK:
        _STATE["index"] = None
        _STATE["building"] = False
        _QUERY_CACHE.clear()


def _set_index(index: DenseIndex | None) -> None:
    with _LOCK:
        _STATE["index"] = index
        _STATE["building"] = False


def _start_background(entries: list[dict[str, Any]], current: DenseIndex | None) -> None:
    with _LOCK:
        if _STATE["building"]:
            return
        _STATE["building"] = True

    snapshot = [dict(e) for e in entries if e.get("rel_path")]

    def _job() -> None:
        try:
            built = _apply_pending(current, snapshot)
            if built is not None:
                _set_index(built)
            else:
                with _LOCK:
                    _STATE["building"] = False
        except Exception:
            log.exception("dense background sync failed")
            with _LOCK:
                _STATE["building"] = False

    threading.Thread(target=_job, daemon=True, name="kb-dense-sync").start()


def sync_from_index(index_data: dict[str, Any], *, blocking: bool | None = None) -> DenseIndex | None:
    """Refresh vectors for current notes_index entries. Non-blocking if too many new notes."""
    entries = [e for e in (index_data.get("entries") or []) if isinstance(e, dict) and e.get("rel_path")]
    model = _embed_model()
    with _LOCK:
        current: DenseIndex | None = _STATE["index"]
    if current is None:
        current = _load_cache(cache_path(), model=model)
        if current is not None:
            _set_index(current)
    keep_paths, keep_hashes, keep_rows, pending = _plan_sync(entries, current, model=model)
    if not pending:
        if current is None:
            return None
        pruned = DenseIndex(
            keep_paths,
            keep_hashes,
            np.stack(keep_rows, axis=0) if keep_rows else current.matrix[:0],
            model=model,
        )
        _set_index(pruned)
        return pruned
    max_inline = _sync_max_notes()
    force_block = blocking is True
    defer = blocking is False or (blocking is None and len(pending) > max_inline)
    if defer and not force_block:
        log.info("dense sync deferred (%d pending, max_inline=%d)", len(pending), max_inline)
        _start_background(entries, current)
        return current
    built = _apply_pending(current, entries)
    if built is not None:
        _set_index(built)
    return built


def search_notes(
    question: str,
    entries: list[dict[str, Any]],
    *,
    top_n: int,
) -> list[str]:
    idx = sync_from_index({"entries": entries}, blocking=None)
    if idx is None or not idx.available:
        return []
    return idx.search(question, top_n=top_n)
