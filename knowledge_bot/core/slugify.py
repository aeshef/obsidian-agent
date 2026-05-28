import re


_ALLOWED = re.compile(r"[^\w\s-]", re.UNICODE)


def make_slug(title: str) -> str:
    s = title.strip()
    s = _ALLOWED.sub("", s)
    s = re.sub(r"\s+", "_", s)
    return s if s else "note"


