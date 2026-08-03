"""Shared LLM-artifact detector — the single gate for text that gets persisted.

Why this exists
---------------
A 2026-08-01 corpus audit found **13.7% of the 89,061 live `spiritual_wisdom`
chunks** (~12,193 chunks across 186 of 391 source videos) carried the extraction
LLM's own chain-of-thought, embedded and retrievable as doctrine. Verbatim, live:

    "Sadhana is a term in the teaching. a common transcription error where a
     space is omitted."

The root cause was not one bad function — it was three validators that each
guarded one path and never the others:

  * ``OKFQualityFilter``            → only ``OKFStore.list_entries()`` (23 entries)
  * ``raptor.py`` topic-label check → only RAPTOR summaries (correct: fail-closed)
  * ``_contains_prompt_leak``       → only ``ingest/corrector.py``

Nothing guarded the Qdrant write path, and ``pipeline._extract_topics`` salvaged
unparseable LLM output through a *blocklist* — which fails open by construction.
So reasoning text became a "topic", was written into the chunk header, embedded,
and served to seekers as teaching.

This module is the shared detector both paths now call, so a pattern added once
is enforced at every persistence point.

Design
------
**High precision over high recall.** Every pattern here is an unambiguous machine
artifact — markdown task scaffolding, explicit self-reference to the prompt, or a
known debug header. Ambiguous natural language is deliberately excluded: "We are
given" appears in real teachings, and deleting doctrine is a worse failure than
keeping one dirty chunk. Rejections are returned with the matched span so they
are auditable, never silently dropped.

**Index-preserving.** ``select_clean`` returns *indices*, not a filtered list, so
callers can realign parallel arrays (metadata, speaker labels). Returning a bare
filtered list is exactly what let ``_embed_and_upsert`` shift every subsequent
chunk's metadata onto the wrong chunk whenever one chunk was dropped.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)

# Unambiguous machine artifacts. Every entry must be text a guru would never say.
# When in doubt, leave it out — a false positive deletes doctrine.
_ARTIFACT_PATTERNS: tuple[str, ...] = (
    # -- markdown task scaffolding emitted by a reasoning model --
    r"\*\*\s*(?:Analyze|Analyse|Conclusion|Deconstruct|Synthesiz|Refine|Brainstorm)",
    r"\*\*\s*Step\s*\d",
    r"^\s*\d+\.\s+\*\*[A-Z][a-z]+ the (?:Input|Text|Sentence|Rules)",
    # -- explicit self-reference to the prompt / task --
    r"\bI(?:'ve| have) been asked to\b",
    r"\bMy task is to\b",
    r"\bI need to (?:analyze|analyse|determine|classify|extract|identify)\b",
    r"\bLet me (?:analyze|analyse|break this|think about)\b",
    r"\bThe user (?:wants me to|has provided|is asking|has essentially)\b",
    r"\bInterpret the Input\b",
    # -- rubric / self-evaluation commentary --
    r"\bThis (?:looks good|fits well|is a classic distinction)\b",
    r"^\s*\*\s+\"[^\"]{2,60}\"\s+-\s+This\b",
    r"\bThis gets to the\b",
    # -- instruction echo from the extraction prompt itself --
    r"\bReturn ONLY a JSON\b",
    r"\bDo NOT include reasoning\b",
    r"\bcomma-separated list\b",
    # -- meta-prompt analysis / topic generation scaffolding --
    r"\bThe system is analyzing\b",
    r"\bCore Task\s*:",
    r"\bThe output format is secondary\b",
    r"\bGenerating a topic label\b",
    r"\bRefining a list of potential topic\b",
    r"\bevaluating (?:several|potential) topic labels\b",
    r"\bDecompose a spiritual teaching\b",
    # -- transcription-correction commentary leaking into the teaching --
    r"\ba common transcription error\b",
    # -- known debug headers / unresolved provenance --
    r"RAPTOR Level\s*:",
    r"_\(Source:\s*unknown\)_",
    r"^\s*>\s*\[Source:",
    r"^\s*>\s*\[RAPTOR",
)

_ARTIFACT_RE = re.compile("|".join(_ARTIFACT_PATTERNS), re.IGNORECASE | re.MULTILINE)


# ASR decoder-loop detection. Whisper's known long-form failure mode is emitting
# a phrase on repeat, most often over silence. The 2026-08-01 audit found this in
# 2.72% of live chunks (~2,422), worst case the word "Each" repeated 3,924 times.
# A vector built from one token repeated thousands of times is not merely useless
# — it sits in a pathological region of the space and can surface for arbitrary
# queries. Regex cannot express "same n-gram many times", so this is a counter.
_LOOP_NGRAM = 5
_LOOP_MIN_REPEATS = 4
_LOOP_MIN_WORDS = 25


def has_repetition_loop(text: str) -> str | None:
    """Return the looping phrase when *text* shows an ASR decoder loop.

    Real teachings repeat for emphasis ("life, life, and life alone"), so the
    threshold is deliberately well above rhetorical repetition: the same 5-word
    window must recur 4+ times within a single chunk.
    """
    if not text:
        return None
    words = text.lower().split()
    if len(words) < _LOOP_MIN_WORDS:
        return None
    counts: dict[str, int] = {}
    for i in range(len(words) - _LOOP_NGRAM + 1):
        gram = " ".join(words[i:i + _LOOP_NGRAM])
        counts[gram] = counts.get(gram, 0) + 1
        if counts[gram] >= _LOOP_MIN_REPEATS:
            return gram
    return None


def find_artifact(text: str) -> str | None:
    """Return the matched artifact span, or ``None`` when *text* is clean.

    Covers both contamination vectors found in the audit: LLM chain-of-thought
    (pattern match) and ASR decoder loops (repetition counter).
    """
    if not text:
        return None
    match = _ARTIFACT_RE.search(text)
    if match:
        return match.group(0).strip()
    loop = has_repetition_loop(text)
    if loop:
        return f"repetition loop: {loop!r}"
    return None


def is_clean(text: str) -> bool:
    """True when *text* carries no detectable LLM artifact."""
    return find_artifact(text) is None


def select_clean(
    chunks: Iterable[str],
) -> tuple[list[int], list[tuple[int, str, str]]]:
    """Partition *chunks* into clean indices and audit-ready rejections.

    Returns ``(keep_indices, rejected)`` where ``rejected`` holds
    ``(index, matched_artifact, chunk_preview)``. Callers filter their own
    parallel arrays by ``keep_indices`` so metadata never drifts off its chunk.
    """
    keep: list[int] = []
    rejected: list[tuple[int, str, str]] = []
    for i, chunk in enumerate(chunks):
        artifact = find_artifact(chunk)
        if artifact is None:
            keep.append(i)
        else:
            rejected.append((i, artifact, (chunk or "")[:80].replace("\n", " ")))
    return keep, rejected


_REPEAT_ALARM_COUNT = 5


def _normalize_for_repeat(text: str) -> str:
    """Casefold + collapse whitespace, so trivial formatting drift still matches."""
    return " ".join((text or "").split()).casefold()


def collapse_repeats(
    texts: Sequence[str],
    sources: Sequence[str] | None = None,
) -> tuple[list[int], list[tuple[str, int, str]]]:
    """Keep the first occurrence of each repeated chunk in one write batch.

    Returns ``(keep_indices, repeats)`` where ``repeats`` holds
    ``(chunk_preview, copies_dropped, source)``, ordered worst-first. Callers
    filter their parallel arrays by ``keep_indices``, same contract as
    :func:`select_clean`.

    Why this is not covered by :func:`has_repetition_loop`: that detects an
    n-gram loop *within* one chunk. A generator stuck in a loop emits the same
    chunk many times over, and each copy is individually innocent — the signal
    only exists across the batch. The 2026-08-01 corpus measurement found
    exactly this: 14,292 redundant copies traced to 2,134 distinct texts, the
    worst being 227 identical copies under one ``source_url`` and one
    ``parent_id`` with consecutive ``chunk_index`` values, whose body was a
    header remnant plus a chain-of-thought topic label and no teaching at all.
    ``make_point_id`` hashes ``chunk_index``, so every copy earned a distinct
    point id and all 227 persisted.

    Duplicates are keyed on ``(normalized_text, source)``: the same sentence
    appearing in two different talks is legitimate repetition of a teaching and
    is kept; the same sentence written twice for one source is redundant by
    construction.
    """


def collapse_repeats(
    texts: Sequence[str],
    sources: Sequence[str] | None = None,
    metadatas: Sequence[dict[str, Any]] | None = None,
) -> tuple[list[int], list[tuple[str, int, str]]]:
    """Collapse duplicate text chunks within a batch.

    Duplicates are keyed on ``(normalized_text, source)``. The same sentence
    appearing in two different talks is legitimate repetition and is kept;
    the same sentence written twice for one source is redundant by
    construction.

    If ``metadatas`` is provided, the highest-authority representative is selected.
    """
    if sources is not None and len(sources) != len(texts):
        raise ValueError(
            f"Length mismatch: texts has {len(texts)} items but sources has {len(sources)} items."
        )
    if metadatas is not None and len(metadatas) != len(texts):
        raise ValueError(
            f"Length mismatch: texts has {len(texts)} items but metadatas has {len(metadatas)} items."
        )

    def _tier_rank(meta: dict[str, Any] | None) -> int:
        if not meta:
            return 0
        tier = str(meta.get("authority_tier", "primary")).lower()
        ranks = {"primary": 3, "secondary": 2, "tertiary": 1}
        return ranks.get(tier, 0)

    seen: dict[tuple[str, str], int] = {}
    dropped: dict[tuple[str, str], int] = {}
    keep: list[int] = []

    for i, text in enumerate(texts):
        source = str(sources[i]) if sources is not None else ""
        key = (_normalize_for_repeat(text), source)
        if not key[0]:
            keep.append(i)  # empty/whitespace chunks are the quality gate's problem
            continue
        if key in seen:
            dropped[key] = dropped.get(key, 0) + 1
            if metadatas is not None:
                prev_idx = seen[key]
                if _tier_rank(metadatas[i]) > _tier_rank(metadatas[prev_idx]):
                    keep_pos = keep.index(prev_idx)
                    keep[keep_pos] = i
                    seen[key] = i
        else:
            seen[key] = i
            keep.append(i)

    repeats = [
        ((texts[seen[key]] or "")[:80].replace("\n", " "), count, key[1])
        for key, count in dropped.items()
    ]
    repeats.sort(key=lambda r: -r[1])
    return keep, repeats


def is_repeat_alarm(repeats: Sequence[tuple[str, int, str]]) -> bool:
    """True when a repeat count is high enough to mean an upstream generator loop.

    A couple of duplicate chunks is ordinary. Five or more copies of one text
    under one source is not redundancy — it is a writer that stopped advancing,
    and the corpus damage is upstream of this gate.
    """
    return any(count >= _REPEAT_ALARM_COUNT for _, count, _ in repeats)


def clean_topic_label(label: str, *, max_len: int = 60) -> str | None:
    """Validate one LLM-produced topic label. ``None`` means reject.

    Positive validation, not a blocklist: a topic is a short noun phrase. Anything
    multi-line, over-long, sentence-shaped, or artifact-bearing is not a topic —
    it is reasoning that leaked. Mirrors the check ``ingest/raptor.py`` already
    applies to RAPTOR summary labels, which is the one place that got it right.
    """
    if not label:
        return None
    cleaned = label.strip().strip('"').strip("'").strip()
    if not cleaned or len(cleaned) > max_len:
        return None
    if "\n" in cleaned or cleaned.count(".") > 1:
        return None
    if cleaned.endswith((":", ",", ";")):
        return None
    if find_artifact(cleaned) is not None:
        return None
    return cleaned


if __name__ == "__main__":  # runnable self-check
    poison = [
        '2.  **Analyze the Input Sentence:** "The State of Contemporary Anxiety."',
        "The rules are for a task that is *not* the one I've been asked to perform.",
        "Sadhana is a term in the teaching. a common transcription error where a space is omitted.",
        "[RAPTOR Level: 1 | Topic: Simple, Foundational Presence]",
        '*   "Ego and Control" - This gets to the *why* behind the flawed view.',
    ]
    doctrine = [
        "In a beautiful state, you are powerful enough to help yourself and help others around you.",
        "Let us observe Nomi a little longer. Anger and confusion have mounted over his ideas of duty.",
        "We are given this life to live in connection, not in division.",
    ]
    for t in poison:
        assert not is_clean(t), f"MISSED artifact: {t!r}"
    for t in doctrine:
        assert is_clean(t), f"FALSE POSITIVE on doctrine: {t!r}"

    keep, rejected = select_clean([poison[0], poison[1], doctrine[0]])
    assert keep == [2], keep
    assert len(rejected) == 2, rejected

    assert clean_topic_label("Nature of Suffering") == "Nature of Suffering"
    assert clean_topic_label("a common transcription error where a space is omitted.") is None
    assert clean_topic_label("x" * 80) is None
    assert clean_topic_label("Wait\nlet me reconsider") is None
    assert clean_topic_label("") is None

    print(f"patterns: {len(_ARTIFACT_PATTERNS)}")
    print(f"poison detected: {len(poison)}/{len(poison)}  false positives: 0/{len(doctrine)}")
    print("text_quality_filter self-check OK")
