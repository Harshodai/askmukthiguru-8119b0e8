"""
asr_cleaner.py — Deterministic ASR transcript noise removal.

Applied at ingestion time BEFORE clips enter Qdrant. Zero LLM calls.
All patterns are deterministic regex over known ASR decoder artifacts.

# ponytail: ingestion-time transcript cleaning — never modifies meaning, only removes noise
"""

from __future__ import annotations

import re
from typing import Any

# Stutter/repetition: 'So, So' 'you know, you know' 'I mean, I mean'
_STUTTER_RE = re.compile(
    r"\b((?:So|Well|Now|Right|Yes|No|Okay|OK)),\s+\1\b"
    r"|\b(you know),\s+you know\b"
    r"|\b(I mean),\s+I mean\b",
    re.IGNORECASE,
)

# False start with repetition: 'It is, it is a' -> 'It is a'
_FALSE_START_RE = re.compile(r"\b(\w+ \w+),\s+\1\b", re.IGNORECASE)

# Multi-pass word repeat regex: 'carried carried' -> 'carried', 'her her' -> 'her', 'you You' -> 'you', 'relationships. relationships.' -> 'relationships.'
_LEGIT_DOUBLES = frozenset({"that", "had", "is", "do"})

_WORD_REPEAT_RE = re.compile(
    r"\b([A-Za-z]{2,})\b([.,;:!?]?)\s+\b\1\b([.,;:!?]?)",
    re.IGNORECASE,
)

# Embedded audience acknowledgment mid-clip: 'Yes. Any time' -> remove the dangling 'Yes.'
_EMBEDDED_ACK_RE = re.compile(r"(?:^|(?<=\. ))(?:Yes|Right|Okay|OK|Sure)\. (?=[A-Z])")

# 'It kind of,' at start of clip — trailing filler
_IT_KIND_OF_RE = re.compile(r"^It kind of, ")

# 'no, no,' repeated negation
_NO_NO_RE = re.compile(r"\bno, no,\s+", re.IGNORECASE)

# Whisper decoder hallucinations & loops
_WHISPER_HALLUCINATIONS = [
    (re.compile(r"\barise eyes\b", re.IGNORECASE), "arise"),
    (re.compile(r"\bproblems would arise eyes\b", re.IGNORECASE), "problems would arise"),
    (re.compile(r"\bthank you for watching\b[.,!?]?", re.IGNORECASE), ""),
    (re.compile(r"\bplease subscribe\b[.,!?]?", re.IGNORECASE), ""),
]

# Ephemeral retreat / meeting date announcements
_RETREAT_DATE_RE = re.compile(
    r"\bIn (?:January|February|March|April|May|June|July|August|September|October|November|December) when we meet,?\s*",
    re.IGNORECASE,
)

# Severed relative clause at clip end: e.g. "from which you perform", "where you would", "which we do"
_SEVERED_TRAILING_CLAUSE_RE = re.compile(
    r"\s*(?:,\s*)?\b(?:from\s+which|in\s+which|to\s+which|where|which|that)\s+"
    r"(?:you|we|they|he|she|i|one)\s+"
    r"(?:perform|would|do|are|is|were|was|have|had|can|could|will|shall|might|should)\s*[.,]?$",
    re.IGNORECASE,
)


# Whole-word ASR restart across punctuation: 'relationships. relationships. are' -> 'relationships are'.
_PUNCT_REPEAT_RE = re.compile(r"\b(\w{5,})[.,]\s+\1\b[.,]?", re.IGNORECASE)

# Case-flipped restart with no punctuation: 'seek Seek the truth' -> 'seek the truth'.
# Only fires when the two words differ in case, so legitimate 'that that' / 'had had' survive.
_CASE_FLIP_REPEAT_RE = re.compile(r"\b(\w{4,})\s+(\1)\b", re.IGNORECASE)


def _drop_case_flip(m: re.Match[str]) -> str:
    return m.group(1) if m.group(1) != m.group(2) else m.group(0)


def clean_verbatim_text(text: str) -> str:
    """Remove ASR noise from verbatim text. Preserves all meaning. Idempotent."""
    if not text:
        return ""
    orig_text = text
    # Remove stutter repeats: 'So, So' -> 'So'
    text = _STUTTER_RE.sub(lambda m: m.group(1) or m.group(2) or m.group(3), text)
    # Remove false starts with repetition
    text = _FALSE_START_RE.sub(lambda m: m.group(1), text)
    # Remove whole-word ASR restarts ('relationships. relationships.', 'seek Seek')
    text = _PUNCT_REPEAT_RE.sub(lambda m: m.group(1), text)
    text = _CASE_FLIP_REPEAT_RE.sub(_drop_case_flip, text)
    # Multi-pass word repeat deduplication: 'carried carried' -> 'carried', 'her her' -> 'her'
    for _ in range(4):

        def _repl(m: re.Match) -> str:
            w1 = m.group(1)
            # 'that that' / 'had had' are grammatical; keep same-case pairs.
            if w1.lower() in _LEGIT_DOUBLES and m.group(0).split()[-1].rstrip(".,;:!?") == w1:
                return m.group(0)
            punct = m.group(3) or m.group(2) or ""
            return f"{w1}{punct}"

        new_text = _WORD_REPEAT_RE.sub(_repl, text)
        if new_text == text:
            break
        text = new_text
    # Remove Whisper hallucinations
    for pat, repl in _WHISPER_HALLUCINATIONS:
        text = pat.sub(repl, text)
    # Remove ephemeral retreat dates
    text = _RETREAT_DATE_RE.sub("", text)
    # Snap/trim severed trailing relative clauses: 'from which you perform'
    text = _SEVERED_TRAILING_CLAUSE_RE.sub(".", text)
    # Collapse accidental double periods without touching ellipsis (...)
    text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)
    # Remove mid-clause filler: ', you know,'
    text = re.sub(r",\s*you know,\s*", ", ", text, flags=re.IGNORECASE)
    # Remove embedded audience acks mid-sentence
    text = _EMBEDDED_ACK_RE.sub("", text)
    # Remove 'It kind of,' opener
    text = _IT_KIND_OF_RE.sub("", text)
    # Remove 'no, no,' filler (leave single 'no')
    text = _NO_NO_RE.sub("no, ", text)
    # Clean up double spaces
    text = re.sub(r"  +", " ", text).strip()
    # Capitalize first char if cleaned from head opener, or if original wasn't lowercase
    stripped_opener = bool(
        _IT_KIND_OF_RE.match(orig_text)
        or _RETREAT_DATE_RE.match(orig_text)
        or _EMBEDDED_ACK_RE.match(orig_text)
    )
    if (
        (stripped_opener or not (orig_text and orig_text.strip()[:1].islower()))
        and text
        and text[0].islower()
    ):
        text = text[0].upper() + text[1:]
    return text


def clean_clips(clips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clean verbatim_text in all clips in-place. Returns clips list."""
    for clip in clips:
        if "verbatim_text" in clip:
            clip["verbatim_text"] = clean_verbatim_text(clip["verbatim_text"])
    return clips


if __name__ == "__main__":
    cases = [
        ("carried carried", "carried"),
        ("her her", "her"),
        ("healing Healing", "healing"),
        ("relationships. relationships.", "relationships."),
        ("you You", "you"),
        ("problems would arise eyes.", "problems would arise."),
        ("In February when we meet,", ""),
        (
            "In February when we meet, you will awaken to the enlightened state of stillness",
            "You will awaken to the enlightened state of stillness",
        ),
        ("So, So the thing is...", "So the thing is..."),
        (
            "You know, when she is sad, you know, you are actually there.",
            "You know, when she is sad, you are actually there.",
        ),
        ("It kind of, any time you feel disturbed.", "Any time you feel disturbed."),
        (
            "He will say, no, no, I want to have my alcohol.",
            "He will say, no, I want to have my alcohol.",
        ),
        (
            "when you were carried carried by destructive emotional states",
            "when you were carried by destructive emotional states",
        ),
        (
            "made her her husband turn back to her life with love",
            "made her husband turn back to her life with love",
        ),
        (
            "Suffering will come problems would arise eyes. But the question is",
            "Suffering will come problems would arise. But the question is",
        ),
        (
            "recognize those destructive emotional states from which you perform",
            "recognize those destructive emotional states.",
        ),
    ]
    passed = 0
    for inp, expected in cases:
        result = clean_verbatim_text(inp)
        status = "✅" if result == expected else "❌"
        print(f"{status} Input:    {inp!r}")
        if result != expected:
            print(f"   Expected: {expected!r}")
            print(f"   Got:      {result!r}")
        else:
            passed += 1
    print(f"\n{passed}/{len(cases)} self-check cases passed")
