"""Weekly reflection files in the vault."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from planning_bot.core.config import REFLECTION_DIR
from planning_bot.core.pdmsg import pdmsg


def _thoughts_header() -> str:
    return (
        pdmsg("reflection_md_thoughts_header")
        or pdmsg("auto_29e747c3bc")
        or "## My thoughts"
    ).strip()


def _reflection_prefix() -> str:
    return (
        pdmsg("reflection_file_prefix")
        or pdmsg("auto_9e853157ef")
        or "Reflection_"
    )


def _reflection_glob() -> str:
    return (
        pdmsg("reflection_glob")
        or pdmsg("auto_9dc5227b7a")
        or "Reflection_*.md"
    )


class ReflectionManager:
    def __init__(self, reflection_dir: Path = REFLECTION_DIR) -> None:
        self.reflection_dir = reflection_dir
        self.reflection_dir.mkdir(parents=True, exist_ok=True)

    def save_weekly_reflection(
        self, review_text: str, user_response: Optional[str] = None
    ) -> None:
        today = datetime.now()
        days_until_sunday = (6 - today.weekday()) % 7
        if days_until_sunday == 0 and today.weekday() != 6:
            sunday = today
        else:
            sunday = today + timedelta(days=days_until_sunday)
        date_s = sunday.strftime("%d.%m.%Y")
        reflection_file = self.reflection_dir / f"{_reflection_prefix()}{sunday.strftime('%Y-%m-%d')}.md"
        title = (
            pdmsg("reflection_md_title", date=date_s)
            or pdmsg("auto_a3ba53a9d0", p1=date_s)
            or f"# Weekly reflection {date_s}\n\n"
        )
        review_header = (
            pdmsg("reflection_md_review_header")
            or "## Assistant review\n\n"
        )
        content = title if title.endswith("\n") else title + "\n"
        content += review_header + review_text + "\n\n"
        if user_response:
            content += _thoughts_header() + "\n\n" + user_response + "\n\n"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        footer = (
            pdmsg("reflection_md_footer", ts=ts)
            or f"---\n\n*Created: {ts}*\n"
        )
        content += footer
        reflection_file.write_text(content, encoding="utf-8")

    def get_previous_reflections_summary(self, limit: int = 5) -> str:
        reflections = sorted(self.reflection_dir.glob(_reflection_glob()), reverse=True)
        if not reflections:
            return ""
        summaries = []
        thoughts_header = _thoughts_header()
        for reflection_file in reflections[:limit]:
            content = reflection_file.read_text(encoding="utf-8")
            # Empty separator: `"" in text` is always True, then str.split("") raises.
            if thoughts_header and thoughts_header in content:
                thoughts = content.split(thoughts_header, 1)[1].split("---")[0].strip()
                if thoughts:
                    summaries.append(f"**{reflection_file.stem}:**\n{thoughts[:300]}...")
                    continue
            # No user-thoughts section — use a short excerpt of the review body.
            body = content.strip()
            if body:
                summaries.append(f"**{reflection_file.stem}:**\n{body[:300]}...")
        return "\n\n".join(summaries)
