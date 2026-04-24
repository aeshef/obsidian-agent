#!/usr/bin/env python3
from __future__ import annotations

from planning_bot.core.pdmsg import pdmsg
import email
import imaplib
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from pathlib import Path
from typing import Any, Dict, List, Optional
from shared.tz import get_tz

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_PARENT = PROJECT_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

log = logging.getLogger("pb.iphone_mail_sync")


def _iphone_sync_tz():
    name = (
        os.environ.get("IPHONE_SYNC_TZ")
        or os.environ.get("SERENDIPITY_TZ")
        or os.environ.get("TIMEZONE")
    )
    return get_tz(name)


def _email_header_datetime(date_str: str) -> Optional[datetime]:
    from email.utils import parsedate_to_datetime

    try:
        return parsedate_to_datetime(date_str)
    except (TypeError, ValueError):
        return None


def _is_header_date_in_recent_window(
    date_header: str, tz: ZoneInfo, recent_days: int
) -> bool:
    'Operation implementation.'
    if recent_days < 1:
        recent_days = 1
    dt = _email_header_datetime(date_header)
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    d = dt.astimezone(tz).date()
    now_d = datetime.now(tz).date()
    delta = (now_d - d).days
    return 0 <= delta < recent_days


from planning_bot.services.iphone_health_fields import (
    extract_raw_fields,
    is_valid_health_snapshot,
    normalize_raw_fields,
    parse_ts as _parse_health_ts,
)


def _decode_mime_header(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value or ""


def _extract_text_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ct = (part.get_content_type() or "").lower()
            disp = (part.get("Content-Disposition") or "").lower()
            if ct == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    payload = msg.get_payload(decode=True) or b""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _parse_ts(s: str) -> Optional[datetime]:
    return _parse_health_ts(s)


def _parse_body(raw_body: str, fallback_ts: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    'Operation implementation.'
    fields = extract_raw_fields(raw_body)
    return normalize_raw_fields(fields, fallback_ts=fallback_ts)


def _snap_to_txt(snap: Dict[str, Any]) -> str:
    'Operation implementation.'
    lines = ["---"]
    for k, v in snap.items():
        if v is None or v == "":
            continue
        if isinstance(v, float):
            # (comment)
            s = f"{v:.4f}".rstrip("0").rstrip(".")
            lines.append(f"{k}: {s}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _snap_filename(snap: Dict[str, Any]) -> Optional[str]:
    'Operation implementation.'
    from planning_bot.services.iphone_snapshot_names import format_snapshot_filename

    ts_str = snap.get("ts", "")
    if not ts_str:
        return None
    try:
        dt = datetime.strptime(ts_str, "%d.%m.%Y, %H:%M")
    except ValueError:
        return None
    return format_snapshot_filename(dt)


def _load_state(state_path: Path) -> Dict[str, Any]:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"processed_ids": []}


def _save_state(state_path: Path, state: Dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def run_iphone_mail_sync(
    *,
    user: Optional[str] = None,
    app_password: Optional[str] = None,
    host: str = "imap.gmail.com",
    port: int = 993,
    subject_filter: str = pdmsg("auto_499df715b7"),
    iphone_dir: Optional[Path] = None,
    state_path: Optional[Path] = None,
    limit: int = 50,
    since_days: int = 30,
    dry_run: bool = False,
    today_only: Optional[bool] = None,
) -> Dict[str, Any]:
    'Operation implementation.'
    from planning_bot.core.config import IPHONE_CONTEXT_DIR

    user = (user or os.environ.get("GMAIL_IMAP_USER", "")).strip()
    app_password = (app_password or os.environ.get("GMAIL_IMAP_APP_PASSWORD", "")).strip()
    # (comment)
    app_password = app_password.replace(" ", "")
    host = os.environ.get("GMAIL_IMAP_HOST", host)
    subject_filter = os.environ.get("GMAIL_IMAP_SUBJECT", subject_filter)

    if not user or not app_password:
        return {"ok": False, "error": "GMAIL_IMAP_USER or GMAIL_IMAP_APP_PASSWORD not set"}

    if today_only is None:
        today_only = os.environ.get("IPHONE_MAIL_SYNC_TODAY_ONLY", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
    try:
        recent_days = int(os.environ.get("IPHONE_MAIL_SYNC_RECENT_DAYS", "2").strip() or "2")
    except ValueError:
        recent_days = 2
    recent_days = max(1, min(recent_days, 14))
    tz = _iphone_sync_tz()

    out_dir = iphone_dir or IPHONE_CONTEXT_DIR
    state_file = state_path or (out_dir / ".sync_state.json")
    out_dir.mkdir(parents=True, exist_ok=True)

    state = _load_state(state_file)
    processed_ids: set = set(state.get("processed_ids", []))

    result: Dict[str, Any] = {
        "ok": True,
        "fetched": 0,
        "written": 0,
        "skipped": 0,
        "rejected": 0,
        "errors": [],
        "today_only": today_only,
        "recent_days": recent_days,
        "timezone": str(tz),
    }

    try:
        imap = imaplib.IMAP4_SSL(host, port)
        imap.login(user, app_password)
    except Exception as e:
        return {"ok": False, "error": f"IMAP connect/auth failed: {e}"}

    try:
        imap.select("INBOX")
        # (comment)
        status, data = imap.search(None, "ALL")
        if status != "OK":
            return {"ok": False, "error": "IMAP SEARCH failed"}

        ids = [x for x in (data[0] or b"").split() if x]
        # (comment)
        cutoff = datetime.now() - timedelta(days=since_days)
        subject_lower = subject_filter.lower()

        matched_ids: List[bytes] = []
        for eid in reversed(ids[-500:]):  # (comment)
            if len(matched_ids) >= limit:
                break
            # (comment)
            s2, hdr = imap.fetch(eid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE MESSAGE-ID)])")
            if s2 != "OK" or not hdr or not hdr[0]:
                continue
            raw_hdr = hdr[0][1] if isinstance(hdr[0], tuple) else None
            if not raw_hdr:
                continue
            h = email.message_from_bytes(raw_hdr)
            subj = _decode_mime_header(h.get("Subject", ""))
            if subject_lower not in subj.lower():
                continue
            date_str = _decode_mime_header(h.get("Date", ""))
            if today_only and not _is_header_date_in_recent_window(
                date_str, tz, recent_days
            ):
                continue
            try:
                from email.utils import parsedate_to_datetime

                email_dt = parsedate_to_datetime(date_str)
                email_naive = email_dt.replace(tzinfo=None)
                if email_naive < cutoff:
                    continue
            except Exception:
                pass
            msg_id = _decode_mime_header(h.get("Message-ID", "")) or eid.decode()
            if msg_id in processed_ids:
                result["skipped"] += 1
                continue
            matched_ids.append((eid, msg_id))

        result["fetched"] = len(matched_ids)
        log.info(pdmsg("auto_a677743480"), len(matched_ids))

        for eid, msg_id in matched_ids:
            try:
                s3, full = imap.fetch(eid, "(RFC822)")
                if s3 != "OK" or not full or not full[0]:
                    continue
                raw = full[0][1]
                msg = email.message_from_bytes(raw)

                date_str = _decode_mime_header(msg.get("Date", ""))
                if today_only and not _is_header_date_in_recent_window(
                    date_str, tz, recent_days
                ):
                    continue
                fallback_ts: Optional[datetime] = None
                try:
                    from email.utils import parsedate_to_datetime

                    _edt = parsedate_to_datetime(date_str)
                    fallback_ts = _edt.replace(tzinfo=None) if _edt.tzinfo else _edt
                except Exception:
                    pass

                body = _extract_text_body(msg)
                snap = _parse_body(body, fallback_ts=fallback_ts)
                if snap is None:
                    log.warning(pdmsg("auto_f467c12287"), msg_id)
                    result["errors"].append(pdmsg("auto_3c7a592b40", _p1=msg_id))
                    continue

                if not is_valid_health_snapshot(snap):
                    log.warning(pdmsg("auto_6f0b8d4c71"), msg_id)
                    result["rejected"] += 1
                    result["errors"].append(pdmsg("auto_5e9a7c3b62", _p1=msg_id))
                    if not dry_run:
                        processed_ids.add(msg_id)
                    continue

                fname = _snap_filename(snap)
                if fname is None:
                    result["errors"].append(pdmsg("auto_4d8b6a2c51", _p1=msg_id))
                    continue

                fpath = out_dir / fname
                txt = _snap_to_txt(snap)
                if not dry_run:
                    fpath.write_text(txt, encoding="utf-8")
                    processed_ids.add(msg_id)
                    result["written"] += 1
                else:
                    print(pdmsg("auto_2b69581a2f", _p1=fname, _p3=txt), end="")
                    result["written"] += 1

                log.info(pdmsg("auto_24a40f8990"), fname)
            except Exception as e:
                log.exception(pdmsg("auto_f2deb0d2f1"), msg_id)
                result["errors"].append(str(e))
    finally:
        try:
            imap.close()
        except Exception:
            pass
        try:
            imap.logout()
        except Exception:
            pass

    if not dry_run:
        state["processed_ids"] = list(processed_ids)
        _save_state(state_file, state)

    result["ok"] = len(result["errors"]) == 0 or result["written"] > 0
    return result


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    ap = argparse.ArgumentParser(description="Fetch iPhone context emails from Gmail IMAP")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--since-days", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--subject", default=pdmsg("auto_499df715b7"))
    ap.add_argument(
        "--all-days",
        action="store_true",
        help=pdmsg("auto_71fa76afac"),
    )
    ap.add_argument(
        "--today-only",
        action="store_true",
        help=pdmsg("auto_38c97b7149"),
    )
    args = ap.parse_args()

    if args.all_days:
        today_only_flag: Optional[bool] = False
    elif args.today_only:
        today_only_flag = True
    else:
        today_only_flag = None  # (comment)

    res = run_iphone_mail_sync(
        limit=args.limit,
        since_days=args.since_days,
        dry_run=args.dry_run,
        subject_filter=args.subject,
        today_only=today_only_flag,
    )
    import json as _json
    print(_json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res.get("ok") else 1)
