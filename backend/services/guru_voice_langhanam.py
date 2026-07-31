"""
Langhanam-inspired unified guru voice for Sri Preethaji & Sri Krishnaji.

Voice definition cleaned from the Langhanam discourse
(https://youtu.be/2z5qxSr4EaI): direct address to the seeker ("I want you
to...", "Listen...", "Try this..."), short rhythmic sentences with
repetition for emphasis, Sanskrit terms kept intact where they carry
meaning (langhanam, vaak Shakti, prana, shuddhi), Indian-English phrasing
("Our ancients in India used one very simple principle..."), no American
conversational fillers ("like", "you know", "basically"), and one teaching
at a time — never a generic blend of all sources.

Two benchmarked variants:
- Variant A (prompt): ``render_langhanam_system_prompt`` injects a voice
  block into the generation system prompt.
- Variant B (adapter): ``rag.nodes.guru_tone_adapter.apply_langhanam_tone``
  rule-based rewrite of the finished answer (filler stripping + cadence).
"""

from __future__ import annotations

import re

# Cleaned reference voice — five paragraphs distilled from the Langhanam
# discourse. Transcription errors ("shittim", "love venoms") are removed;
# the direct-address rhythm and Sanskrit terms are preserved verbatim.
REFERENCE_VOICE = """
If you want mental, emotional, spiritual and physical health, practice langhanam.
Our ancients in India used one very simple principle. They called it langhanam.
Langhanam means fasting — fasting is the ultimate medicine.
Listen to the end before you come to any conclusion.

The first langhanam is fasting from food. Eat only when your digestive fire actually burns and asks for it, not when your tongue asks. This will also give some rest to the one cooking at home.
Digest most effectively when your breath flows strongly through your right nostril, because of the solar energy flow.
Practice any kind of fasting you can. Intermittent fasting, water fasting, or soup fasting. Even animals fast when they are sick.

The second langhanam is fasting from breath. Every cell is an engine powered by the intake of breath. Practice slow inhalations and extremely long exhalations with breath pauses. Your thoughts will become more positive.

The third langhanam is fasting from hurtful and pessimistic speech. Very few people have vaak Shakti, the power of speech to manifest their goals. Speak words that are true, that cause joy to others, in a pleasing tone. Your vaak Shakti grows.

The fourth langhanam is fasting from movement. It is not about lying on your cushion eating popcorn and watching television. Sit still. Observe your breath, listen to the sounds of nature, or chant the name of your divine being inwardly. Even one minute at a time will bring down the restlessness in your body and mind.

Langhanam is power. Practice these four fasts, and you will feel great power in your body, mind and consciousness.
""".strip()

# Voice block appended to the generation system prompt (variant A).
LANGHANAM_VOICE_BLOCK = """
When you speak as the guru, use this voice:
- Speak directly to the seeker in short, rhythmic sentences.
- Use Sanskrit terms naturally: langhanam, vaak Shakti, prana, shuddhi.
- Phrase things as our ancients in India would teach: simple, direct, embodied.
- Avoid American fillers: like, you know, basically, totally, I think, kind of.
- Do not combine or genericize teachings. Stay with the one teaching the seeker asked about.
- Be gentle, but command attention. Repetition is allowed for emphasis.
""".strip()

# American conversational fillers to avoid (word-boundary, case-insensitive).
# "kind of"/"sort of" are only fillers when NOT preceded by a determiner —
# "any kind of fasting" is Indian-English, "kind of tired" is a filler.
LANGHANAM_FILLERS: tuple[str, ...] = (
    "like",
    "you know",
    "basically",
    "totally",
    "i think",
    "kind of",
    "sort of",
    "i mean",
    "you know what i mean",
    "honestly",
    "literally",
)

# Sanskrit / teaching terms that carry meaning and must stay intact.
LANGHANAM_SANSKRIT_TERMS: tuple[str, ...] = (
    "langhanam",
    "vaak shakti",
    "vaak",
    "prana",
    "shuddhi",
    "deeksha",
    "aham",
)

# Intents eligible for the guru voice: teaching/doctrine queries and
# distress. Pure factual lookup-only queries (FACTUAL) are excluded so a
# voice rewrite never muffles a direct fact. COMPARATIVE joins RELATIONAL
# as a teaching-bearing intent in the graph's taxonomy (intent.py routes
# DEEP/TEMPORAL/CAPABILITY into FACTUAL, which stays excluded).
LANGHANAM_ELIGIBLE_INTENTS: frozenset[str] = frozenset(
    {"TEACHING", "DOCTRINE", "QUERY", "COMPARATIVE", "RELATIONAL", "DISTRESS"}
)

# Stacked fixed-width negative lookbehinds: "kind of"/"sort of" are only
# fillers when NOT preceded by a determiner ("any kind of fasting" is
# Indian-English, "kind of tired" is a filler).
_DETERMINER_LOOKBEHIND = (
    r"(?<!a )(?<!an )(?<!any )(?<!some )(?<!each )(?<!every )(?<!many )(?<!one )"
)

_FILLER_RE = re.compile(
    r"\b(?:" + "|".join(
        _DETERMINER_LOOKBEHIND + re.escape(f) if f in ("kind of", "sort of") else re.escape(f)
        for f in LANGHANAM_FILLERS
    ) + r")\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_DIRECT_ADDRESS_RE = re.compile(
    r"\b(?:i want you to|listen|try this|notice|observe|imagine|practice)\b",
    re.IGNORECASE,
)
_COMBINED_TEACHINGS_RE = re.compile(
    r"\b(?:in another teaching|another teaching|other teachings|similarly|"
    r"in addition|on the other hand)\b",
    re.IGNORECASE,
)
_SANSKRIT_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in LANGHANAM_SANSKRIT_TERMS) + r")\b",
    re.IGNORECASE,
)


def count_fillers(text: str) -> int:
    """Count American conversational filler occurrences in ``text``."""
    if not text:
        return 0
    return len(_FILLER_RE.findall(text))


def strip_fillers(text: str) -> str:
    """Remove American conversational fillers from ``text``."""
    if not text:
        return text
    cleaned = _FILLER_RE.sub("", text)
    cleaned = re.sub(r",\s*,", ",", cleaned)
    cleaned = re.sub(r"\.\s*,", ".", cleaned)
    cleaned = re.sub(r"\s+([.,!?;])", r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.lstrip(",;:—–").strip()


def split_sentences(text: str) -> list[str]:
    """Split ``text`` into non-empty sentences on terminal punctuation."""
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def mean_sentence_length(text: str) -> float:
    """Mean words-per-sentence over ``text`` (0.0 for empty input)."""
    sentences = split_sentences(text)
    if not sentences:
        return 0.0
    return sum(len(s.split()) for s in sentences) / len(sentences)


def has_direct_address(text: str) -> bool:
    """True when ``text`` addresses the seeker directly."""
    return bool(text and _DIRECT_ADDRESS_RE.search(text))


def contains_sanskrit_terms(text: str) -> bool:
    """True when ``text`` keeps at least one meaningful Sanskrit term."""
    return bool(text and _SANSKRIT_RE.search(text))


def detect_combined_teachings(text: str) -> list[str]:
    """Return combining markers found in ``text`` (empty = single teaching)."""
    if not text:
        return []
    return list(dict.fromkeys(_COMBINED_TEACHINGS_RE.findall(text.lower())))


def render_langhanam_system_prompt(base_system_prompt: str) -> str:
    """Variant A: append the Langhanam voice block to a system prompt."""
    if not base_system_prompt:
        return LANGHANAM_VOICE_BLOCK
    return f"{base_system_prompt.rstrip()}\n\n{LANGHANAM_VOICE_BLOCK}"


def is_voice_eligible(intent: str) -> bool:
    """True when ``intent`` should receive the guru voice.

    Teaching/doctrine queries and distress qualify; pure factual
    lookup-only queries (FACTUAL) are excluded.
    """
    return (intent or "").upper() in LANGHANAM_ELIGIBLE_INTENTS


if __name__ == "__main__":
    sample = (
        "I want you to listen carefully. Basically, you know, langhanam "
        "is fasting. Try this practice and observe your breath."
    )
    print(f"fillers detected: {count_fillers(sample)}")
    print(f"after strip_fillers: {strip_fillers(sample)!r}")
    print(f"direct address: {has_direct_address(sample)}")
    print(f"sanskrit terms: {contains_sanskrit_terms(sample)}")
    print(f"mean sentence length: {mean_sentence_length(sample):.1f} words")
    print(f"combined teachings: {detect_combined_teachings('similar teachings also say')}")
    print(f"render appends block: {'use this voice' in render_langhanam_system_prompt('base')}")
    print(f"eligible: {is_voice_eligible('DISTRESS')}, not eligible: {is_voice_eligible('FACTUAL')}")
    print("guru_voice_langhanam self-check OK")
