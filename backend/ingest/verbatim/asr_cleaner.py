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

# Embedded audience acknowledgment mid-clip: 'Yes. Any time' -> remove the dangling 'Yes.'
_EMBEDDED_ACK_RE = re.compile(r"(?:^|(?<=\. ))(?:Yes|Right|Okay|OK|Sure)\. (?=[A-Z])")

# 'It kind of,' at start of clip — trailing filler
_IT_KIND_OF_RE = re.compile(r"^It kind of, ")

# 'no, no,' repeated negation
_NO_NO_RE = re.compile(r"\bno, no,\s+", re.IGNORECASE)


# Whole-word ASR restart across punctuation: 'relationships. relationships. are' -> 'relationships are'.
_PUNCT_REPEAT_RE = re.compile(r"\b(\w{5,})[.,]\s+\1\b[.,]?", re.IGNORECASE)

# Case-flipped restart with no punctuation: 'seek Seek the truth' -> 'seek the truth'.
# Only fires when the two words differ in case, so legitimate 'that that' / 'had had' survive.
_CASE_FLIP_REPEAT_RE = re.compile(r"\b(\w{4,})\s+(\1)\b", re.IGNORECASE)


def _drop_case_flip(m: re.Match[str]) -> str:
    return m.group(1) if m.group(1) != m.group(2) else m.group(0)


def clean_verbatim_text(text: str) -> str:
    """Remove ASR noise from verbatim text. Preserves all meaning. Idempotent."""
    # Remove stutter repeats: 'So, So' -> 'So'
    text = _STUTTER_RE.sub(lambda m: m.group(1) or m.group(2) or m.group(3), text)
    # Remove false starts with repetition
    text = _FALSE_START_RE.sub(lambda m: m.group(1), text)
    # Remove whole-word ASR restarts ('relationships. relationships.', 'seek Seek')
    text = _PUNCT_REPEAT_RE.sub(lambda m: m.group(1), text)
    text = _CASE_FLIP_REPEAT_RE.sub(_drop_case_flip, text)
    # Remove embedded audience acks mid-sentence
    text = _EMBEDDED_ACK_RE.sub("", text)
    # Remove 'It kind of,' opener
    text = _IT_KIND_OF_RE.sub("", text)
    # Remove 'no, no,' filler (leave single 'no')
    text = _NO_NO_RE.sub("no, ", text)
    # Clean up double spaces
    text = re.sub(r"  +", " ", text).strip()
    # Capitalize first char if cleaned
    if text and text[0].islower():
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
