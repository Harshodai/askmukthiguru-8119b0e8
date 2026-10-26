"""Stage: ASR-agreement gate.

Ported from `scripts/ops/build_first_person_index.py`'s ``MIN_ASR_AGREEMENT``
threshold and ``asr_agreement()`` reasoning: whisper-vs-parakeet word
agreement below this means the transcript may hold words never spoken (pilot
low: AK435vKMtlo at 0.064; bake-off videos span 0.855-0.941, so 0.80 only cuts
outliers). Provisional -- the owner can move it.

This module holds the pure threshold check on an already-computed
``vote_stage()`` result; it does not re-read any file, so it has no opinion on
where the agreement rate came from.
"""

from __future__ import annotations

import collections
import re
import unicodedata
from typing import Any, Optional

MIN_ASR_AGREEMENT = 0.80


def _char_in_script(ch: str, expected_script: str) -> bool:
    base_chars = [
        c for c in unicodedata.normalize("NFKD", ch) if unicodedata.category(c).startswith("L")
    ]
    if not base_chars:
        return True
    exp = expected_script.upper()
    return any(exp in unicodedata.name(c, "") for c in base_chars)


def _script_of(ch: str) -> Optional[str]:
    """Script name prefix of a letter (``LATIN``, ``DEVANAGARI``, ``CYRILLIC``...)."""
    for c in unicodedata.normalize("NFKD", ch):
        if unicodedata.category(c).startswith("L"):
            name = unicodedata.name(c, "")
            return name.split(" ", 1)[0] if name else None
    return None


def dominant_script(text: str) -> Optional[str]:
    """Most common Unicode script among the letters of ``text`` (``None`` if unknown).

    Used to decide whether an English-only ASR stage may run at all, so it needs a
    script, not a language: Devanagari here cannot be told apart as Hindi or
    Marathi, and it does not need to be."""
    names = [script for script in (_script_of(ch) for ch in text if ch.isalpha()) if script]
    if not names:
        return None
    return collections.Counter(names).most_common(1)[0][0]


def script_and_loop_problem(text: str, expected_script: Optional[str] = "Latin") -> Optional[str]:
    """Return a quarantine reason if text has mixed scripts (>2%) or ASR decoder loops.

    ``expected_script=None`` means "infer the dominant script of this span": a wholly
    Devanagari, Telugu or Tamil span then passes, while a span that mixes scripts
    (the D1 Urdu+Latin+Cyrillic garbage) is still refused. Serve-time callers use
    ``None`` because the product is multilingual; builders for the English corpus
    keep the explicit ``"Latin"``.
    """
    if not text or not text.strip():
        return None

    # 1. Any non-separator character run of 6 or more
    for m in re.finditer(r"(\S)\1{5,}", text):
        ch = m.group(1)
        if ch not in "-_=.~#*":
            return f"asr_char_loop:{ch * 6}"

    # 2. Same word repeated 5 or more times
    words = re.findall(r"\b\w+\b", text, flags=re.UNICODE)
    if words:
        run = 1
        prev = words[0].lower()
        for w in words[1:]:
            wl = w.lower()
            if wl == prev:
                run += 1
                if run >= 5:
                    return f"asr_word_loop:{prev}"
            else:
                run = 1
                prev = wl

    # 3. More than 2% characters outside the expected (or dominant) script
    letter_chars = [ch for ch in text if unicodedata.category(ch).startswith(("L", "M"))]
    if letter_chars:
        target = expected_script
        if target is None:
            counts = collections.Counter(
                script for script in (_script_of(ch) for ch in letter_chars) if script
            )
            if not counts:
                return None
            target = counts.most_common(1)[0][0]
        foreign = [ch for ch in letter_chars if not _char_in_script(ch, target)]
        foreign_ratio = len(foreign) / len(letter_chars)
        if foreign_ratio > 0.02:
            sample = "".join(foreign[:5])
            return f"asr_script_garbage:foreign_ratio={foreign_ratio:.3f}:{sample}"

    return None


def check_asr_agreement(
    vote_result: dict[str, Any], min_agreement: float = MIN_ASR_AGREEMENT
) -> Optional[str]:
    """Return a quarantine reason string, or None if the video clears the gate."""
    if not vote_result.get("ok"):
        return "asr_agreement_unknown"
    rate = vote_result.get("agreement_rate")
    if not isinstance(rate, (int, float)):
        return "asr_agreement_unknown"
    if rate < min_agreement:
        return f"asr_agreement_low:{rate:.3f}"
    return None


def _self_check() -> None:
    assert check_asr_agreement({"ok": True, "agreement_rate": 0.95}) is None
    assert check_asr_agreement({"ok": True, "agreement_rate": 0.5}) == "asr_agreement_low:0.500"
    assert check_asr_agreement({"ok": False}) == "asr_agreement_unknown"
    assert check_asr_agreement({"ok": True}) == "asr_agreement_unknown"
    print("gates.py self-check OK")


if __name__ == "__main__":
    _self_check()
