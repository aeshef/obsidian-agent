#!/usr/bin/env python3
"""Seed Knowledge + Handwritten for demo-vault-en (EN tags, wikilinks for graph).

Creates only synthetic EN notes
with cross-links so Obsidian Graph looks dense on film.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

KNOWLEDGE = "Knowledge"
HANDWRITTEN = "600_Handwritten"

def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.lstrip("\n") if body.startswith("\n") else body, encoding="utf-8")
    if not body.endswith("\n"):
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    print(f"  wrote {path}")


def seed_synthetic_knowledge(vault: Path) -> list[str]:
    """EN synthetic notes with deliberate [[wikilinks]] for a dense graph."""
    titles: list[str] = []
    pack = [
        (
            "Notes/Deep_Work_Blocks.md",
            "note",
            "Deep work blocks",
            ["domain/study", "topic/productivity", "topic/focus"],
            """
Pair 90-minute focus blocks with a written outcome. See [[Agent_Budgets]] for context budgets
and [[Weekly_Review_Template]] for the Sunday reset. When energy dips, use [[I_love_it_method]].
""",
        ),
        (
            "Notes/Context_Switching_Tax.md",
            "note",
            "Context switching tax",
            ["domain/study", "topic/productivity"],
            """
Every switch costs ~15 minutes of ramp. Batch similar work. Related: [[Deep_Work_Blocks]],
[[Meetings_and_week_focus]] on the dashboards hub, [[Life_OS_Film_Beats]].
""",
        ),
        (
            "Notes/Second_Brain_Capture.md",
            "note",
            "Second brain capture",
            ["domain/study", "topic/pkm", "topic/obsidian"],
            """
Capture → clarify → organize → reflect → engage. Park raw clips in Inbox, then promote to
[[Reading_List]] or [[Life_OS_Index]]. Handwritten freewrites live in [[Morning_Pages_Sample]].
""",
        ),
        (
            "Notes/Sleep_Debt_Rule.md",
            "note",
            "Sleep debt rule",
            ["domain/health", "topic/sleep"],
            """
Protect a 7h floor on weekdays. Pair with [[Walk_8k_habit]] and nutrition notes.
Dashboard: Health hub tracks sleep stages next to [[Deep_Work_Blocks]].
""",
        ),
        (
            "Notes/Walk_8k_habit.md",
            "note",
            "Walk 8k habit",
            ["domain/health", "topic/habits"],
            """
Default loop: harbor path after lunch. See [[Harbor_Park]] and [[Overnight_Oats]] for fuel.
""",
        ),
        (
            "Ideas/Chart_in_Telegram_Hero.md",
            "idea",
            "Chart in Telegram hero",
            ["domain/career", "topic/product", "topic/demo"],
            """
One question → answer → PNG in chat → same PNG in vault. See [[Life_OS_Film_Beats]] and
[[Tasks_and_spending]] chart under Cross analytics.
""",
        ),
        (
            "Ideas/Budget_Quality_Gate.md",
            "idea",
            "Budget quality gate",
            ["domain/infrastructure", "topic/agents", "topic/eval"],
            """
Pareto clip_ratio vs answer quality. Related: [[Agent_Budgets]], [[Knowledge_distillation_модели]].
""",
        ),
        (
            "Ideas/Graph_View_Demo.md",
            "idea",
            "Graph view demo",
            ["domain/career", "topic/obsidian", "topic/demo"],
            """
For film: open Graph, filter tags `domain/study` and `topic/productivity`. Hubs:
[[Life_OS_Index]], [[Reading_List]].
""",
        ),
        (
            "Books/Staff_Engineer.md",
            "book",
            "Staff Engineer",
            ["domain/study", "topic/books", "topic/career"],
            """
Status vs growth tracks. Pair with [[Designing_Data_Intensive_Apps]] and [[Atomic_Habits]].
""",
        ),
        (
            "Books/Thinking_in_Systems.md",
            "book",
            "Thinking in Systems",
            ["domain/study", "topic/books", "topic/systems"],
            """
Stocks, flows, feedback. Maps cleanly onto kanban CFD. See [[Open_by_category_days]] idea in
[[Graph_View_Demo]].
""",
        ),
        (
            "Books/The_Creative_Act.md",
            "book",
            "The Creative Act",
            ["domain/growth", "topic/books", "topic/creativity"],
            """
Practice over inspiration. Link: [[Morning_Pages_Sample]], [[Whiteboard_Q3_Sketch]].
""",
        ),
        (
            "Places/Quiet_Cafe_North.md",
            "place",
            "Quiet Cafe North",
            ["domain/experience", "topic/places", "topic/focus"],
            """
Laptop-friendly mornings. Pair with [[Northside_Library]] and [[Deep_Work_Blocks]].
""",
        ),
        (
            "Places/River_Trail.md",
            "place",
            "River Trail",
            ["domain/health", "topic/places", "topic/habits"],
            """
Evening walk loop for [[Walk_8k_habit]]. Nearby [[Harbor_Park]].
""",
        ),
        (
            "Recipes/Sheet_Pan_Salmon.md",
            "recipe",
            "Sheet pan salmon",
            ["domain/home", "topic/food", "topic/recipes"],
            """
Salmon + broccoli + lemon, 18 min at 200°C. Meal prep with [[Overnight_Oats]].
""",
        ),
        (
            "Recipes/Black_Bean_Tacos.md",
            "recipe",
            "Black bean tacos",
            ["domain/home", "topic/food"],
            """
Weeknight default. Grocery list lives next to [[Coffee_Shops]].
""",
        ),
        (
            "Courses/Fast_AI_Practical.md",
            "course",
            "Fast.ai practical",
            ["domain/study", "topic/courses", "topic/ml"],
            """
Lesson notes + mini-projects. Related: [[Computer_vision_basketball]], [[Applied_Category_Theory]].
""",
        ),
        (
            "Courses/System_Design_Primer.md",
            "course",
            "System design primer",
            ["domain/career", "topic/courses", "topic/systems"],
            """
Caches, queues, consistency. Read alongside [[Designing_Data_Intensive_Apps]].
""",
        ),
        (
            "Films/Arrival.md",
            "film",
            "Arrival",
            ["domain/experience", "topic/films"],
            """
Language shapes thought. Pair with [[The_Creative_Act]] and [[Cambridge_intellectual_capital]].
""",
        ),
        (
            "Films/Whiplash.md",
            "film",
            "Whiplash",
            ["domain/experience", "topic/films", "topic/motivation"],
            """
Intensity vs sustainability. Contrast with [[I_love_it_method]] reframing.
""",
        ),
        (
            "Thoughts/Energy_Not_Time.md",
            "thought",
            "Energy not time",
            ["domain/growth", "topic/reflection"],
            """
Schedule high-cognition work to peak energy. See [[Strategy_Interests]] handwritten note and
[[Sleep_Debt_Rule]].
""",
        ),
        (
            "Thoughts/Shipping_Beats_Perfect.md",
            "thought",
            "Shipping beats perfect",
            ["domain/career", "topic/reflection"],
            """
Demo film needs one hero beat, not seven. [[Life_OS_Film_Beats]], [[Chart_in_Telegram_Hero]].
""",
        ),
        (
            "Sources/PG_Essays_Index.md",
            "source",
            "PG essays index",
            ["domain/study", "topic/sources", "topic/essays"],
            """
Cities and ambition → [[Cambridge_intellectual_capital]]. Maker schedule ↔ [[Deep_Work_Blocks]].
""",
        ),
        (
            "Sources/Agent_Eval_Notes.md",
            "source",
            "Agent eval notes",
            ["domain/infrastructure", "topic/agents", "topic/eval"],
            """
Gold baskets + Pareto. See [[Budget_Quality_Gate]] and [[Agent_Budgets]].
""",
        ),
        (
            "_Hubs/PKM_Map.md",
            "hub",
            "PKM map",
            ["hub", "topic/pkm", "topic/obsidian"],
            """
# PKM map

## Capture
- [[Second_Brain_Capture]]
- [[Morning_Pages_Sample]]

## Think
- [[Deep_Work_Blocks]]
- [[Energy_Not_Time]]
- [[I_love_it_method]]

## Build
- [[Agent_Budgets]]
- [[Budget_Quality_Gate]]
- [[System_Design_Primer]]

## Live
- [[Walk_8k_habit]]
- [[Harbor_Park]]
- [[Sheet_Pan_Salmon]]

## Watch / read
- [[Reading_List]]
- [[Arrival]]
- [[Thinking_in_Systems]]
""",
        ),
    ]
    for rel, typ, title, tags, body in pack:
        path = vault / KNOWLEDGE / rel
        tag_line = "[" + ", ".join(tags) + "]"
        _write(
            path,
            f"""---
type: {typ}
title: {title}
created: 2026-08-01
tags: {tag_line}
summary: Synthetic demo note for graph / film
---

# {title}

{body.strip()}
""",
        )
        titles.append(title)
    return titles


def seed_handwritten(vault: Path) -> int:
    """Handwritten folder: synthetic EN reflections."""
    n = 0
    today = date.today()

    reflections = [
        (
            "Weekly_Shipping_Note.md",
            "Ship one vertical slice. Hero beat > feature list. See [[Life_OS_Film_Beats]].",
        ),
        (
            "Focus_Tax_Journal.md",
            "Counted 11 context switches before lunch. Tomorrow: [[Deep_Work_Blocks]] only until 12.",
        ),
        (
            "Walk_After_Lunch.md",
            "River loop felt better than coffee #2. Track with [[Walk_8k_habit]] / [[River_Trail]].",
        ),
        (
            "Story_Beats_Sketch.md",
            "Drama · detail · hero. Telegram chart reveal. [[Chart_in_Telegram_Hero]].",
        ),
        (
            "Budget_Clip_Ratio.md",
            "Clip ratio spiked on vault dumps — tighten tool_result_max_chars. [[Agent_Budgets]].",
        ),
        (
            "Reading_Stack.md",
            "This week: [[Thinking_in_Systems]], [[Staff_Engineer]]. Drop one book if unfinished.",
        ),
        (
            "Kitchen_Default.md",
            "Default dinners: [[Sheet_Pan_Salmon]], [[Black_Bean_Tacos]], [[Overnight_Oats]].",
        ),
        (
            "Library_Morning.md",
            "Northside quiet floor 2. Pair with [[Quiet_Cafe_North]] on noisy days.",
        ),
        (
            "Reframe_Failure.md",
            "PR rejected → story fuel. Practice [[I_love_it_method]].",
        ),
        (
            "Sunday_Reset.md",
            "Wins / stuck / next 3. Template: [[Weekly_Review_Template]].",
        ),
    ]
    for i, (name, body) in enumerate(reflections):
        d = (today - timedelta(days=3 * i)).isoformat()
        _write(
            vault / HANDWRITTEN / name,
            f"""---
title: {name.replace('_', ' ').removesuffix('.md')}
created: {d}
tags: [handwritten, reflection, demo]
---

# {name.replace('_', ' ').removesuffix('.md')}

{body}
""",
        )
        n += 1

    # Dated reflection stubs (graph + calendar feel)
    for i in range(1, 9):
        d = today - timedelta(days=7 * i)
        _write(
            vault / HANDWRITTEN / "Reflection" / f"Reflection_{d.isoformat()}.md",
            f"""---
title: Reflection {d.isoformat()}
created: {d.isoformat()}
tags: [handwritten, reflection, weekly]
---

# Reflection {d.isoformat()}

## Wins
- Closed a meaningful WIP slice
- Kept the walk habit ([[Walk_8k_habit]])

## Stuck
- Too many parallel threads — see [[Context_Switching_Tax]]

## Next
- One deep block ([[Deep_Work_Blocks]])
- One knowledge note promoted from inbox ([[Second_Brain_Capture]])
""",
        )
        n += 1

    # Keep earlier sample names for hub links
    _write(
        vault / HANDWRITTEN / "Morning_Pages_Sample.md",
        """---
title: Morning pages sample
created: 2026-08-22
tags: [handwritten, demo, morning]
---

# Morning pages sample

Clear the mental inbox before [[Deep_Work_Blocks]]. Related: [[Sunday_Reset]], [[Strategy_Interests]].
""",
    )
    _write(
        vault / HANDWRITTEN / "Whiteboard_Q3_Sketch.md",
        """---
title: Whiteboard Q3 sketch
created: 2026-08-19
tags: [handwritten, planning, demo]
---

# Whiteboard Q3 sketch

Ship demo → film → OSS launch. Hero: [[Chart_in_Telegram_Hero]]. Scope: [[Life_OS_Film_Beats]].
""",
    )
    _write(
        vault / HANDWRITTEN / "Meeting_Doodle_Standup.md",
        """---
title: Meeting doodle standup
created: 2026-08-27
tags: [handwritten, meetings, demo]
---

# Meeting doodle standup

Blockers: sandbox access. Next: onboarding rewrite. See [[System_Design_Primer]].
""",
    )
    n += 3
    return n


def seed_knowledge_pack(vault: Path) -> None:
    """Entry: synthetic knowledge and handwritten notes."""
    for sub in (
        "Notes",
        "Books",
        "Places",
        "Recipes",
        "Ideas",
        "Courses",
        "Films",
        "Thoughts",
        "Sources",
        "_Hubs",
        "_Attachments",
    ):
        (vault / KNOWLEDGE / sub).mkdir(parents=True, exist_ok=True)
    (vault / HANDWRITTEN / "Reflection").mkdir(parents=True, exist_ok=True)

    synth = seed_synthetic_knowledge(vault)
    hand = seed_handwritten(vault)

    # Refresh hubs with denser links
    _write(
        vault / KNOWLEDGE / "_Hubs" / "Life_OS_Index.md",
        """---
type: hub
title: Life OS index
created: 2026-08-01
tags: [hub, demo]
---

# Life OS index

- Tasks → [[📋 Task_Board]]
- Goals → [[🎯 2026_Goals]]
- Finance → [[📊 Finance_Dashboard]]
- Health → [[🏥 Health]]
- Analytics → [[🔬 Analytics]]
- PKM → [[PKM_Map]]
- Knowledge → [[Trip_Plan]], [[Coffee_Shops]], [[Second_Brain_Capture]]
- Handwritten → [[Morning_Pages_Sample]], [[Strategy_Interests]]
""",
    )
    _write(
        vault / KNOWLEDGE / "_Hubs" / "Reading_List.md",
        """---
type: hub
title: Reading list
created: 2026-08-02
tags: [hub, books, demo]
---

# Reading list

- [[Designing_Data_Intensive_Apps]]
- [[Atomic_Habits]]
- [[Thinking_in_Systems]]
- [[Staff_Engineer]]
- [[The_Creative_Act]]
- [[Wealth_of_Nations]]
""",
    )
    print(f"  knowledge pack: copied=0 synthetic={len(synth)} handwritten={hand}")
