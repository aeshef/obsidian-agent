#!/usr/bin/env python3
from __future__ import annotations

import argparse
import email
import imaplib
import os
import sys
from email.header import decode_header, make_header
from getpass import getpass


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _extract_text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            content_type = (part.get_content_type() or "").lower()
            disp = (part.get("Content-Disposition") or "").lower()
            if content_type == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                try:
                    return payload.decode(charset, errors="replace")
                except Exception:
                    return payload.decode("utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    charset = msg.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except Exception:
        return payload.decode("utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser(description="Test fetch iPhone context emails from Gmail via IMAP")
    ap.add_argument("--host", default="imap.gmail.com")
    ap.add_argument("--port", type=int, default=993)
    ap.add_argument("--mailbox", default="INBOX")
    ap.add_argument("--subject", default="Контекст_IPhone")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--user", default=os.getenv("GMAIL_IMAP_USER", ""))
    ap.add_argument("--app-password", default=os.getenv("GMAIL_IMAP_APP_PASSWORD", ""))
    args = ap.parse_args()

    user = args.user.strip()
    if not user:
        user = input("Gmail address: ").strip()
    if not user:
        print("No user provided.", file=sys.stderr)
        return 2

    app_password = args.app_password.strip() or getpass("Gmail app password (16 chars): ")
    if not app_password:
        print("No app password provided.", file=sys.stderr)
        return 2

    try:
        imap = imaplib.IMAP4_SSL(args.host, args.port)
        imap.login(user, app_password)
    except imaplib.IMAP4.error as e:
        print(f"IMAP auth failed: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"IMAP connection failed: {e}", file=sys.stderr)
        return 1

    try:
        status, _ = imap.select(args.mailbox)
        if status != "OK":
            print(f"Cannot select mailbox: {args.mailbox}", file=sys.stderr)
            return 1

        # IMAP SEARCH в imaplib по умолчанию ASCII-only; кириллица в SUBJECT
        # даёт UnicodeEncodeError. Поэтому берём ALL и фильтруем тему уже в Python.
        status, data = imap.search(None, "ALL")
        if status != "OK":
            print("Search failed.", file=sys.stderr)
            return 1

        ids = [x for x in (data[0] or b"").split() if x]
        if not ids:
            print("Mailbox is empty.")
            return 0

        subject_need = (args.subject or "").strip().lower()
        matched: list[bytes] = []
        # Идём с конца (самые новые), сначала тянем только заголовки.
        for eid in reversed(ids):
            status, msg_data = imap.fetch(eid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            if not raw:
                continue
            msg = email.message_from_bytes(raw)
            subj = _decode_header(msg.get("Subject"))
            if subject_need in subj.lower():
                matched.append(eid)
            if len(matched) >= args.limit:
                break

        if not matched:
            print(f'No matching emails found for subject contains: "{args.subject}"')
            return 0

        matched.reverse()  # Выводим от более старого к более новому.
        print(f"Found at least {len(matched)} matching emails. Showing {len(matched)}:\n")
        for eid in matched:
            status, msg_data = imap.fetch(eid, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            if not raw:
                continue
            msg = email.message_from_bytes(raw)
            subj = _decode_header(msg.get("Subject"))
            from_ = _decode_header(msg.get("From"))
            date_ = _decode_header(msg.get("Date"))
            body = _extract_text(msg).strip()
            print("=" * 80)
            print(f"ID: {eid.decode(errors='ignore')}")
            print(f"Date: {date_}")
            print(f"From: {from_}")
            print(f"Subject: {subj}")
            print("-" * 80)
            print(body[:2000] if body else "(empty text/plain body)")
            print()
    finally:
        try:
            imap.close()
        except Exception:
            pass
        imap.logout()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
