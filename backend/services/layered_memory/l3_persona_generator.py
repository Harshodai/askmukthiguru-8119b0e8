"""L3 persona generation — user-stated preferences and interests synthesis (T6-03 / MEM-004)."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from services.layered_memory.models import MemoryAtom

logger = logging.getLogger(__name__)

# MEM-004 remainder: no LLM writes the persona. It is compiled from the
# user-stated atoms by compile_user_preferences and rendered as a list of the
# atoms' own text. Nothing is inferred (no stage, diagnosis or profile).
_SECTIONS = (
    ("stated_topics", "Stated topics and interests"),
    ("explicit_preferences", "Explicit preferences"),
    ("practices_undertaken", "Practices undertaken"),
)
_MAX_ITEMS_PER_SECTION = 10


def compile_user_preferences(atoms: list[MemoryAtom]) -> dict[str, list[str]]:
    """T6-03 (MEM-004): Extract structured, factual user-stated preferences directly from atoms."""
    topics: list[str] = []
    preferences: list[str] = []
    practices: list[str] = []

    for a in atoms:
        content = a.content.strip()
        if not content:
            continue
        atom_type = (a.type or "").lower()
        if atom_type in ("preference", "pref"):
            preferences.append(content)
        elif atom_type in ("practice", "meditation", "sadhana"):
            practices.append(content)
        elif atom_type in ("topic", "interest", "persona"):
            topics.append(content)
        else:
            topics.append(content)

    return {
        "stated_topics": topics,
        "explicit_preferences": preferences,
        "practices_undertaken": practices,
    }


def render_user_preferences(prefs: dict[str, list[str]]) -> str:
    """Markdown list of the compiled preferences, de-duplicated, order kept."""
    blocks: list[str] = []
    for key, title in _SECTIONS:
        items: list[str] = []
        for item in prefs.get(key) or []:
            if item not in items:
                items.append(item)
        if items:
            lines = [f"## {title}"] + [f"- {i}" for i in items[:_MAX_ITEMS_PER_SECTION]]
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


async def generate_persona(atoms: list[MemoryAtom], existing_persona: Optional[str] = None) -> str:
    """Persona text from user-stated atoms only (MEM-004). No LLM call.

    With no usable atoms the existing persona is returned unchanged, so callers
    that save only non-empty text do not overwrite it.
    """
    rendered = render_user_preferences(compile_user_preferences(list(atoms or [])))
    return rendered or (existing_persona or "")


if __name__ == "__main__":
    sample = [MemoryAtom("User meditates 20 min daily", "persona", 90, [], "Morning Practice", {})]
    print(asyncio.run(generate_persona(sample)))
