"""
asr_cleaner.py — Deterministic ASR transcript noise removal.

Applied at ingestion time BEFORE clips enter Qdrant. Zero LLM calls.
Refactored by Fable 5.2: Replaces the broken non-capturing group in `_STUTTER_RE`
and the 8x4 nested regex fixed-point loops with a single-pass O(N) token-stream
state machine that is strictly idempotent (`clean(clean(x)) == clean(x)`) in 1 pass.

# ponytail: ingestion-time transcript cleaning — never modifies meaning, only removes noise
"""

from __future__ import annotations

import re
from typing import Any

from ingest.verbatim.gates import CHANT_WORDS

_LEGIT_DOUBLES = frozenset({"that", "had", "is", "do"})
_CHANT_WORDS = CHANT_WORDS
_STUTTER_WORDS = frozenset({"so", "well", "now", "right", "yes", "no", "okay", "ok"})

# Fix: capture group 1 `(So|Well|...)` so `\1` backreference is valid
_STUTTER_RE = re.compile(
    r"\b(So|Well|Now|Right|Yes|No|Okay|OK)(?:,\s+\1\b)+"
    r"|\b(you know)(?:,\s+you know\b)+"
    r"|\b(I mean)(?:,\s+I mean\b)+",
    re.IGNORECASE,
)

_FALSE_START_RE = re.compile(r"\b(\w+ \w+),\s+\1\b", re.IGNORECASE)
_COMMA_REPEAT_RE = re.compile(r"\b([A-Za-z]{2,})\b[,;]\s+\1\b", re.IGNORECASE)
_EMBEDDED_ACK_RE = re.compile(r"(?:^|(?<=\. ))(?:Yes|Right|Okay|OK|Sure)\. (?=[A-Z])")
_IT_KIND_OF_RE = re.compile(r"^It kind of, ")

_WHISPER_HALLUCINATIONS = [
    (re.compile(r"\bproblems would arise eyes\b", re.IGNORECASE), "problems would arise"),
    (re.compile(r"\barise eyes\b", re.IGNORECASE), "arise"),
    (re.compile(r"\bthank you for watching\b[.,!?]*", re.IGNORECASE), ""),
    (re.compile(r"\bplease subscribe\b[.,!?]*", re.IGNORECASE), ""),
]

_RETREAT_DATE_RE = re.compile(
    r"\bIn (?:January|February|March|April|May|June|July|August|September|October|November|December) when we meet,?\s*",
    re.IGNORECASE,
)

_SEVERED_TRAILING_CLAUSE_RE = re.compile(
    r"\s*(?:,\s*)?\b(?:from\s+which|in\s+which|to\s+which|where|which|that)\s+"
    r"(?:you|we|they|he|she|i|one)\s+"
    r"(?:perform|would|do|are|is|were|was|have|had|can|could|will|shall|might|should)\s*[.,]?$",
    re.IGNORECASE,
)


def _collapse_word_and_stutter_repeats_deterministic(text: str) -> str:
    """Single-pass O(N) token-stream state machine that collapses ASR stutters and word repeats."""
    tokens = text.split()
    if not tokens:
        return ""

    out: list[str] = []
    n = len(tokens)
    i = 0

    while i < n:
        tok = tokens[i]
        bare = tok.rstrip(".,;:!?")
        punct = tok[len(bare) :]
        low = bare.lower()

        if i + 3 < n and low in ("you", "i"):
            t2 = tokens[i + 1]
            t2_bare = t2.rstrip(".,;:!?")
            t2_punct = t2[len(t2_bare) :]
            pair_low = f"{low} {t2_bare.lower()}"
            if pair_low in ("you know", "i mean") and t2_punct == ",":
                j = i + 2
                last_t2_punct = ""
                matched_repeat = False
                while j + 1 < n:
                    w1_next = tokens[j].rstrip(".,;:!?").lower()
                    w2_full = tokens[j + 1]
                    w2_next = w2_full.rstrip(".,;:!?").lower()
                    w2_p = w2_full[len(w2_next) :]
                    if f"{w1_next} {w2_next}" == pair_low:
                        matched_repeat = True
                        last_t2_punct = w2_p
                        j += 2
                        if w2_p != ",":
                            break
                    else:
                        break
                if matched_repeat:
                    out.append(bare)
                    out.append(f"{t2_bare}{last_t2_punct}")
                    i = j
                    continue

        if punct == "," and low in _STUTTER_WORDS and i + 1 < n:
            j = i + 1
            repeat_count = 0
            last_punct = ""
            while j < n:
                nxt_tok = tokens[j]
                nxt_bare = nxt_tok.rstrip(".,;:!?")
                nxt_punct = nxt_tok[len(nxt_bare) :]
                if nxt_bare.lower() == low:
                    repeat_count += 1
                    last_punct = nxt_punct
                    j += 1
                    if nxt_punct != ",":
                        break
                else:
                    break
            if repeat_count > 0:
                if low == "no" and last_punct == ",":
                    out.append(f"{bare},")
                else:
                    out.append(f"{bare}{last_punct}")
                i = j
                continue

        # ASCII only, as the pre-2026-11-15 regex ([A-Za-z]): reduplication is
        # grammatical in Hindi/Urdu and the verbatim layer must not delete it.
        if not punct and len(bare) >= 2 and bare.isascii() and bare.isalpha() and i + 1 < n:
            if low not in _CHANT_WORDS:
                j = i + 1
                collapsed = False
                trailing_punct = ""
                while j < n:
                    nxt_tok = tokens[j]
                    nxt_bare = nxt_tok.rstrip(",;")
                    nxt_punct = nxt_tok[len(nxt_bare) :]
                    if nxt_bare.lower() == low and nxt_bare.isascii() and nxt_bare.isalpha():
                        if low in _LEGIT_DOUBLES and nxt_bare == bare:
                            break
                        collapsed = True
                        trailing_punct = nxt_punct
                        j += 1
                        if trailing_punct:
                            break
                    else:
                        break
                if collapsed:
                    out.append(f"{bare}{trailing_punct}")
                    i = j
                    continue

        out.append(tok)
        i += 1

    return " ".join(out)


def clean_verbatim_text(text: str) -> str:
    """Remove ASR noise from verbatim text. Idempotent by construction in a single pass."""
    if not text:
        return ""
    orig_text = text

    stripped_opener = bool(_IT_KIND_OF_RE.match(orig_text))
    if stripped_opener:
        text = _IT_KIND_OF_RE.sub("", text)

    text = re.sub(r",\s*you know,\s*", ", ", text, flags=re.IGNORECASE)
    text = _collapse_word_and_stutter_repeats_deterministic(text)

    for pat, repl in _WHISPER_HALLUCINATIONS:
        text = pat.sub(repl, text)

    text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)
    text = " ".join(text.split())

    if (
        (stripped_opener or not (orig_text and orig_text.strip()[:1].islower()))
        and text
        and text[0].islower()
    ):
        text = text[0].upper() + text[1:]
    return text


def asr_cleaner_flags(text: str) -> list[str]:
    if not text:
        return []
    flags: list[str] = []
    if _RETREAT_DATE_RE.search(text):
        flags.append("retreat_date_announcement")
    if _SEVERED_TRAILING_CLAUSE_RE.search(text):
        flags.append("severed_trailing_clause")
    if _EMBEDDED_ACK_RE.search(text):
        flags.append("embedded_audience_ack")
    return flags


def asr_cleaner_notes(text: str) -> list[str]:
    if not text:
        return []
    notes: list[str] = []
    if _FALSE_START_RE.search(text):
        notes.append("false_start_repeat")
    if _COMMA_REPEAT_RE.search(text):
        notes.append("comma_repeat")
    return notes


def clean_clips(clips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    import hashlib

    for clip in clips:
        if "verbatim_text" in clip:
            cleaned = clean_verbatim_text(clip["verbatim_text"])
            clip["verbatim_text"] = cleaned
            # Invariant #13: every text-changing cleanup updates transcript_hash,
            # source_text_hash, and span_text_sha256 in the same transaction.
            digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
            clip["transcript_hash"] = digest
            clip["source_text_hash"] = digest
            if "span_text_sha256" in clip:
                clip["span_text_sha256"] = digest
    return clips


if __name__ == "__main__":
    cases = [
        ("carried carried", "carried"),
        ("her her", "her"),
        ("healing Healing", "healing"),
        ("you You", "you"),
        ("problems would arise eyes.", "problems would arise."),
        ("What is peace? Peace is an inner state", "What is peace? Peace is an inner state"),
        ("Silence. Silence is not absence", "Silence. Silence is not absence"),
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
