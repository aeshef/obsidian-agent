"""Weekly reflection files in the vault."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from planning_bot.core.config import REFLECTION_DIR
from planning_bot.core.pdmsg import pdmsg


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
        prefix = pdmsg("reflection_file_prefix")
        reflection_file = self.reflection_dir / f"{prefix}{sunday.strftime('%Y-%m-%d')}.md"
        content = pdmsg("reflection_md_title", date=sunday.strftime("%d.%m.%Y"))
        content += pdmsg("reflection_md_review_header") + review_text + "\n\n"
        if user_response:
            content += pdmsg("reflection_md_thoughts_header") + user_response + "\n\n"
        content += pdmsg(
            "reflection_md_footer", ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        reflection_file.write_text(content, encoding="utf-8")

    def get_previous_reflections_summary(self, limit: int = 5) -> str:
        reflections = sorted(
            self.reflection_dir.glob(pdmsg("reflection_glob")), reverse=True
        )
        if not reflections:
            return ""
        summaries = []
        thoughts_header = pdmsg("reflection_md_thoughts_header")
        for reflection_file in reflections[:limit]:
            content = reflection_file.read_text(encoding="utf-8")
            if thoughts_header in content:
                thoughts = content.split(thoughts_header, 1)[1].split("---")[0].strip()
                if thoughts:
                    summaries.append(f"**{reflection_file.stem}:**\n{thoughts[:300]}...")
        return "\n\n".join(summaries)
