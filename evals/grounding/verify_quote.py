#!/usr/bin/env python3
"""Verbatim-quote checker — PLAN.md Phase B2.

Checks whether a claimed quote actually appears in its cited source. Unlike
B1's tier-3 harness, this doesn't need the live backend or an LLM — it needs
ground-truth source text, which exists on disk right now: `transcripts/
<video_id>.md` at repo root (763 files, raw YouTube transcript text fetched
by the ingestion pipeline — see AGENTS.md's Aug 27 corpus-ingestion handoff).

This is deliberately NOT checked against `memory/okf/*.md` — OKF entries are
LLM-synthesized summaries with occasional LLM-*reconstructed* "Quotes:"
blocks (present in only 2 of 715 entries, checked directly before writing
this), not verbatim transcript text. Checking a citation against another
LLM's paraphrase of the source would validate nothing. `transcripts/` is the
closest on-disk approximation to what Qdrant's indexed chunks actually
derive from (pre-chunking, pre-embedding).

What this validates: the mechanical question "does this exact string (or a
whitespace/punctuation-normalized version of it) appear in the named
source's transcript?" What it does NOT validate: whether the *live system*
actually produces citations that pass this check — that needs a running
backend generating real answers, which doesn't exist in this environment
(Railway is scaled to $0 — see root CLAUDE.md). The self-check below proves
the checker itself works correctly (true positives from real transcript
excerpts, true negatives from paraphrased/altered versions), not that the
product's citations are faithful — that's the part still blocked on a live
backend, same limitation as B1's tier 0-2 scenarios.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSCRIPTS_DIR = REPO_ROOT / "transcripts"

_TRANSCRIPT_HEADER_RE = re.compile(r"^##\s*Transcript\s*$", re.MULTILINE)


def _normalize(text: str) -> str:
    """Collapse whitespace and drop punctuation for a forgiving-but-still-
    meaningfully-verbatim comparison. A citation that only differs from the
    source by curly-vs-straight quotes or double spaces should still count
    as verbatim; a citation that adds/removes/reorders words should not."""
    text = text.lower()
    text = re.sub(r"[’‘'\"“”]", "'", text)
    text = re.sub(r"[^\w\s']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_transcript_body(video_id: str, transcripts_dir: Path = TRANSCRIPTS_DIR) -> str | None:
    """Return the transcript text for a video_id, or None if the file/section is missing."""
    path = transcripts_dir / f"{video_id}.md"
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8")
    match = _TRANSCRIPT_HEADER_RE.search(raw)
    if not match:
        return None
    return raw[match.end() :].strip()


@dataclass(frozen=True)
class QuoteVerification:
    quote: str
    video_id: str
    transcript_found: bool
    matched: bool
    method: str  # "exact" | "normalized" | "not_found" | "no_transcript"


def verify_verbatim_quote(
    quote: str, video_id: str, transcripts_dir: Path = TRANSCRIPTS_DIR
) -> QuoteVerification:
    """Check whether `quote` appears verbatim (or whitespace/punctuation-
    normalized) inside the transcript for `video_id`."""
    body = extract_transcript_body(video_id, transcripts_dir)
    if body is None:
        return QuoteVerification(quote, video_id, False, False, "no_transcript")

    if quote in body:
        return QuoteVerification(quote, video_id, True, True, "exact")

    if _normalize(quote) in _normalize(body):
        return QuoteVerification(quote, video_id, True, True, "normalized")

    return QuoteVerification(quote, video_id, True, False, "not_found")


_SPEAKER_HEADER_RE = re.compile(r"^\*\*Speaker:\*\*\s*(.+)$", re.MULTILINE)


def extract_declared_speaker(video_id: str, transcripts_dir: Path = TRANSCRIPTS_DIR) -> str | None:
    """Return the transcript file's own `**Speaker:**` header value, e.g.
    "Sri Krishnaji" or "Sri Preethaji & Sri Krishnaji" (a jointly-spoken
    video). None if the file/field is missing."""
    path = transcripts_dir / f"{video_id}.md"
    if not path.is_file():
        return None
    match = _SPEAKER_HEADER_RE.search(path.read_text(encoding="utf-8"))
    return match.group(1).strip() if match else None


def verify_attribution(
    claimed_teacher: str, video_id: str, transcripts_dir: Path = TRANSCRIPTS_DIR
) -> bool:
    """Hallucinated-attribution check (B2): does the teacher a citation
    claims to quote actually appear as this source's declared speaker?
    A jointly-spoken video's Speaker field lists both teachers, so a claim
    of either one is valid there — only a claim of a teacher who is not
    listed at all is a hallucinated attribution."""
    declared = extract_declared_speaker(video_id, transcripts_dir)
    if declared is None:
        return False
    return _normalize(claimed_teacher) in _normalize(declared)


def precision_recall_f1(cited: set[str], relevant: set[str]) -> dict[str, float]:
    """Standard IR metrics for a citation set (B2's "citation precision and
    recall"). `cited` = source ids the answer actually cited; `relevant` =
    source ids that should have been cited (ground truth). Pure function,
    no I/O — the caller supplies both sets, whether from a live answer or a
    synthetic test case."""
    if not cited and not relevant:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not cited:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    if not relevant:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    true_positives = len(cited & relevant)
    precision = true_positives / len(cited)
    recall = true_positives / len(relevant)
    f1 = 0.0 if (precision + recall) == 0 else 2 * precision * recall / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


if __name__ == "__main__":
    # ponytail: runnable self-check against REAL transcript files, not mocks.
    # Picks a known-substantive transcript, extracts a real sentence as a
    # guaranteed true positive, constructs an altered version as a
    # guaranteed true negative, and checks a nonexistent video_id fails
    # closed rather than silently passing.
    _TEST_VIDEO_ID = "x-mTRlE0TC4"
    _body = extract_transcript_body(_TEST_VIDEO_ID)
    assert _body is not None, "fixture transcript file missing — did transcripts/ move?"

    # A real, exact substring from the transcript (see the file directly).
    _real_quote = "Individual transformation is at the crux of our work."
    _result = verify_verbatim_quote(_real_quote, _TEST_VIDEO_ID)
    assert _result.matched, f"true positive failed: {_result}"
    print(f"PASS true positive (exact): {_result.method}")

    # Same sentence with curly quotes / extra whitespace — should still match via normalization.
    _messy_quote = "Individual  transformation   is at the crux of our work."
    _result2 = verify_verbatim_quote(_messy_quote, _TEST_VIDEO_ID)
    assert _result2.matched, f"normalized true positive failed: {_result2}"
    print(f"PASS true positive (normalized): {_result2.method}")

    # A plausible-sounding but NOT actually present sentence — must not match.
    _fabricated_quote = "Individual transformation is the only path to enlightenment."
    _result3 = verify_verbatim_quote(_fabricated_quote, _TEST_VIDEO_ID)
    assert not _result3.matched, f"false positive: {_result3}"
    print(f"PASS true negative: {_result3.method}")

    # A citation against a video_id with no transcript file — must fail closed, not raise.
    _result4 = verify_verbatim_quote("anything", "NONEXISTENT_VIDEO_ID_123")
    assert not _result4.matched and _result4.method == "no_transcript", f"bad fail-open: {_result4}"
    print(f"PASS missing-transcript fails closed: {_result4.method}")

    # Attribution checks: x-mTRlE0TC4.md declares Speaker: Sri Krishnaji.
    assert verify_attribution("Sri Krishnaji", _TEST_VIDEO_ID), "true attribution failed"
    assert verify_attribution("sri krishnaji", _TEST_VIDEO_ID), (
        "case-insensitive attribution failed"
    )
    assert not verify_attribution("Sri Preethaji", _TEST_VIDEO_ID), (
        "hallucinated attribution not caught"
    )
    assert not verify_attribution("Sri Krishnaji", "NONEXISTENT_VIDEO_ID_123"), (
        "attribution check should fail closed on missing source"
    )
    print(
        "PASS attribution checks (true match, case-insensitive, hallucination caught, fail-closed)"
    )

    # precision_recall_f1 sanity checks.
    assert precision_recall_f1({"a", "b"}, {"a", "b", "c"}) == {
        "precision": 1.0,
        "recall": 2 / 3,
        "f1": 0.8,
    }
    assert precision_recall_f1(set(), set()) == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    assert precision_recall_f1({"x"}, set()) == {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    print("PASS precision_recall_f1 sanity checks")

    print("\nAll evals/grounding/verify_quote.py self-checks passed.")
