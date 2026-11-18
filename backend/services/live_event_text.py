"""Live-event crowd instructions: one pattern for every answer path.

A recorded festival or satsang carries stage directions ("close your eyes",
"Participants should rest their hands upon their thighs with palms facing
downwards", "turn your attention towards the screen"). They are not teachings
and answer no question. The first-person Tier-2 gate rejected them, but the
chat path's excerpt fallback had its own copy of nothing, and on 2026-10-05
(live s4) it quoted the hands-on-thighs instruction as the answer to a
question about detachment. Both paths now import this one pattern.

Ritual/funeral exemption (2026-11-18): "close your eyes" and similar phrases
in a moksha, departure, or funeral-chant context are spiritual guidance for the
dying, not crowd directions. RITUAL_GUIDANCE_CONTEXT_RE detects that surrounding
text to exempt the clip from the live-event gate.
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

# When LIVE_EVENT_INSTRUCTION_RE matches, check whether the surrounding text
# reveals a ritual/funeral/moksha context — if so, the phrase is spiritual
# guidance for the dying, not a stage direction for a live crowd.
# This exemption fires ONLY when a ritual keyword sits in the same sentence as
# the matched instruction AND the passage carries no explicit crowd address.
_RITUAL_GUIDANCE_CONTEXT_RE = re.compile(
    r"(?:"
    r"\bdeparting\b|"
    r"\bthose\s+who\s+are\s+(?:dying|leaving|departing)\b|"
    r"\bmoksha\b|"
    r"\bfuneral\b|"
    r"\bchant\s+to\s+be\s+sung\b|"
    r"\bsung\s+to\s+those\b|"
    r"\bjourney\s+to\s+the\s+(?:light|divine)\b|"
    r"\bdivine\s+(?:guru|light|mother|father)\s+take\b|"
    r"\bfor\s+the\s+(?:dying|deceased|departed)\b"
    r")",
    re.IGNORECASE,
)


_SENTENCE_BREAK_RE = re.compile(r"[.!?]+\s*")

# Explicit stage-direction markers address a room. A ritual word elsewhere in
# the passage must not suppress these: "All of you in the audience, please
# raise your hand" is a crowd instruction no matter what else the clip says.
_CROWD_ADDRESS_RE = re.compile(
    r"(?:"
    r"sneaking\s+a\s+peek|"
    r"\braise\s+your\s+hands?\b|"
    r"\ball\s+of\s+you\b|"
    r"\bthose\s+of\s+you\b|"
    r"\baudience\b|"
    r"\bmicrophone\b|"
    r"\bapplause\b|"
    r"\bcamera\b|"
    r"\beveryone\s+(?:here|in\s+this)\b|"
    r"\bin\s+this\s+(?:hall|room)\b|"
    r"\bfront\s+row\b|"
    r"\bplease\s+be\s+seated\b|"
    r"\bparticipants\s+should\b"
    r")",
    re.IGNORECASE,
)


def _ritual_exemption_applies(text: str, instruction: re.Match[str]) -> bool:
    """True only when the matched instruction is itself ritual guidance.

    Narrower than "a ritual word exists somewhere in the clip": the ritual
    keyword must share the instruction's sentence, and an explicit crowd
    address anywhere in the passage cancels the exemption.
    """
    if _CROWD_ADDRESS_RE.search(text):
        return False
    start = instruction.start()
    previous_break = None
    for previous_break in _SENTENCE_BREAK_RE.finditer(text, 0, start):
        pass
    sentence_start = previous_break.end() if previous_break is not None else 0
    next_break = _SENTENCE_BREAK_RE.search(text, start)
    sentence_end = next_break.start() if next_break is not None else len(text)
    return _RITUAL_GUIDANCE_CONTEXT_RE.search(text, sentence_start, sentence_end) is not None


def is_live_event_instruction(text: str) -> bool:
    """True when ``text`` contains a stage direction to a live audience.

    Returns False when the matching phrase appears in a ritual/moksha/funeral
    context — such occurrences are spiritual guidance for the dying, not crowd
    control.  The exemption requires at least one ``_RITUAL_GUIDANCE_CONTEXT_RE``
    keyword in the same text block.
    """
    if not text:
        return False
    for instruction in LIVE_EVENT_INSTRUCTION_RE.finditer(text):
        if not _ritual_exemption_applies(text, instruction):
            return True
    return False


if __name__ == "__main__":
    assert is_live_event_instruction(
        "Participants should rest their hands upon their thighs with palms facing downwards."
    )
    assert not is_live_event_instruction("When you are hurt, you dissolve your hurt.")
    # Ritual/moksha exemption
    assert not is_live_event_instruction(
        "You may now close your eyes and listen to this chant to be sung to those who are departing."
    )
    # Crowd-direction with ritual keyword in an unrelated clause must still reject
    assert is_live_event_instruction(
        "Please close your eyes. I still see a few sneaking a peek. "
        "Now let us breathe deeply and enter the space of stillness."
    )
    # Mixed context: an explicit crowd address cancels a ritual word elsewhere
    assert is_live_event_instruction(
        "All of you in the audience, please close your eyes and raise your hand "
        "if you have heard the chant to be sung to those who are departing."
    )
    print("live_event_text ok")
