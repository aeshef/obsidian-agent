"""Archive only durably accepted Gmail messages, using stable IMAP UIDs."""
import re


def message_uid(fetch_metadata):
    match=re.search(rb'\bUID (\d+)\b',fetch_metadata if isinstance(fetch_metadata,bytes) else b'')
    return match.group(1) if match else None


def archive_accepted(imap, uid):
    if uid is None: raise ValueError('missing_uid_for_archive')
    status,_=imap.uid('STORE',uid,'-X-GM-LABELS',r'(\Inbox)')
    if status!='OK':raise RuntimeError('gmail_archive_failed')
