"""Live-event crowd instructions: one pattern for every answer path.

A recorded festival or satsang carries stage directions ("close your eyes",
"Participants should rest their hands upon their thighs with palms facing
downwards", "turn your attention towards the screen"). They are not teachings
and answer no question. The first-person Tier-2 gate rejected them, but the
chat path's excerpt fallback had its own copy of nothing, and on 2026-10-05
(live s4) it quoted the hands-on-thighs instruction as the answer to a
question about detachment. Both paths now import this one pattern.
"""

from __future__ import annotations

import re

LIVE_EVENT_INSTRUCTION_RE = re.compile(
    r"(?:"
    r"close your eyes|"
    r"open your eyes|"
    r"(?:with|keep|keeping)\s+(?:your|our)\s+eyes\s+closed|"
    r"sneaking a peek|"
    r"let us begin|"
    r"let's begin|"
    r"take a deep breath|"
    r"sit comfortably|"
    r"sit in stillness|"
    r"hands on your lap|"
    r"\brest\s+(?:your|their|our)\s+hands\b|"
    r"\bpalms?\s+facing\b|"
    r"\bparticipants\s+(?:should|may|must|will|can|are\s+requested)\b|"
    r"\b(?:turn|bring)\s+your\s+attention\s+(?:to|towards)\s+the\s+screen\b|"
    r"thank you all for|"
    r"please be seated|"
    r"good morning everyone|"
    r"good evening everyone|"
    r"welcome everyone|"
    r"raise your hand|"
    r"how many of you"
    r")",
    re.IGNORECASE,
)


def is_live_event_instruction(text: str) -> bool:
    """True when ``text`` contains a stage direction to a live audience."""
    return bool(text) and bool(LIVE_EVENT_INSTRUCTION_RE.search(text))


if __name__ == "__main__":
    assert is_live_event_instruction(
        "Participants should rest their hands upon their thighs with palms facing downwards."
    )
    assert not is_live_event_instruction("When you are hurt, you dissolve your hurt.")
    print("live_event_text ok")
