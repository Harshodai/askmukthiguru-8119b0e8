"""Injection screen for transcript text (NEW-AI-5, AI-010).

Looks for text that addresses a language model: instruction overrides, fake
role markers, scoring or ranking directives, prompt-exfiltration requests and
fence tags. Ordinary teaching language is not a match: "act as a witness",
"forget the past", "ignore the mind's chatter" all pass.

Use: flag for review. D-PG16 (owner decision 2026-11-07): flag only, never
drop a span. The serving lane drops a flagged clip only when
``first_person_injection_screen_drop_enabled`` is set; the offline builder
only records flagged spans in its run manifest.

Known gap: patterns are English. Indic-script and transliterated variants
need native-speaker review before they are added (D-22). The model-side
fence (``services/untrusted.py``) is the control; this screen is a signal.
"""

from __future__ import annotations

import re
import unicodedata

from services.untrusted import has_unneutralised_tag

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction_override",
        re.compile(
            r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|the\s+|any\s+|your\s+)?"
            r"(?:previous|prior|above|earlier|system|these)\s+"
            r"(?:instructions?|rules?|prompts?|context|directions)\b"
        ),
    ),
    (
        "role_marker",
        re.compile(r"(?:^|\n)\s*(?:system|assistant)\s*:|<\|im_start\|>|\[/?inst\]"),
    ),
    (
        "model_address",
        re.compile(
            r"\b(?:you\s+are|you're)\s+(?:now\s+)?(?:an?\s+)?"
            r"(?:ai|assistant|language\s+model|chatbot|llm|scorer|ranker|selector)\b"
            r"|\b(?:dear|attention|hey)\s+(?:ai|assistant|model|llm|scorer|ranker)\b"
        ),
    ),
    (
        "scoring_directive",
        re.compile(
            r"\b(?:score|rank|rate|select)\s+(?:every|all|each|this|the)\s+"
            r"(?:clips?|spans?|passages?|candidates?)\b"
            r"|\breply\s+(?:only\s+with|with\s+(?:only|just|json|the\s+(?:number|index|ids?)|\d))"
            r"|\b(?:output|return|respond\s+with)\s+only\s+"
            r"(?:json|the\s+(?:number|index|ids?)|\d|a\s+(?:number|list))"
        ),
    ),
    (
        "prompt_exfiltration",
        re.compile(
            r"\b(?:print|reveal|show|repeat|output)\s+(?:me\s+)?(?:your|the)\s+"
            r"(?:system\s+)?(?:prompt|instructions)\b"
        ),
    ),
)

_FENCE_TAGS = (
    "clip",
    "span",
    "user_input",
    "user_memory",
    "retrieved_context",
    "conversation_summary",
    "untrusted_source",
    "system",
    "assistant",
    "instructions",
)


def screen(text: str) -> tuple[str, ...]:
    """Return the names of the patterns ``text`` matches (empty when clean)."""
    if not text:
        return ()
    folded = unicodedata.normalize("NFKC", text).casefold()
    hits = [name for name, rx in _PATTERNS if rx.search(folded)]
    if any(has_unneutralised_tag(text, tag) for tag in _FENCE_TAGS):
        hits.append("fence_tag")
    return tuple(hits)
