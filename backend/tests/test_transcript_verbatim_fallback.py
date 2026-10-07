"""Transcript-projection fallback for find_verbatim (2026-10-03).

Phase 3 quote-gate evidence: 16/32 checked quotes reported not_found solely
because their videos (TqxxCYnAxo8 TEDxKC, RAOQ3ZubQGM, vARTudIEq30) have no
word-timestamp corpus dir under scripts/ingestion/corpus/ — the quotes ARE
verbatim in transcripts/<video_id>.md. Deleting them would have destroyed
genuine teachings; this test pins the fallback that keeps them verifiable.

Rules pinned here:
  * corpus index wins when present (it has timestamps)
  * transcript-only videos verify as verbatim with start=end=None
    (no guessed t= — a fabricated timestamp is worse than none)
  * fabricated quotes still fail closed through the fallback
  * video with neither source -> not_found
"""

from __future__ import annotations

import pytest

from services import transcript_verbatim as tv


@pytest.fixture()
def transcripts_root(tmp_path, monkeypatch):
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setattr(tv, "TRANSCRIPTS_ROOT", root)
    return root


def test_transcript_fallback_verbatim_no_timestamps(tmp_path, transcripts_root):
    (transcripts_root / "vidT1.md").write_text(
        "The most important choice is from which state do we live our life.",
        encoding="utf-8",
    )
    result = tv.find_verbatim(
        "the most important choice is from which state do we live our life",
        "vidT1",
        corpus_root=tmp_path / "empty_corpus",
    )
    assert result["status"] == "verbatim"
    assert result["start"] is None and result["end"] is None
    assert result["score"] == 1.0


def test_transcript_fallback_fabricated_still_fails(tmp_path, transcripts_root):
    (transcripts_root / "vidT2.md").write_text(
        "Inner peace comes from observing the breath gently.",
        encoding="utf-8",
    )
    result = tv.find_verbatim(
        "The secret to eternal happiness is gold hidden in silence.",
        "vidT2",
        corpus_root=tmp_path / "empty_corpus",
    )
    assert result["status"] == "not_found"


def test_neither_source_fails_closed(tmp_path, transcripts_root):
    result = tv.find_verbatim(
        "anything at all here", "vidGONE", corpus_root=tmp_path / "empty_corpus"
    )
    assert result["status"] == "not_found"
    assert result["score"] == 0.0


def test_corpus_index_wins_over_transcript(tmp_path, transcripts_root):
    """When the corpus dir exists it stays authoritative (timestamps)."""
    vid = tmp_path / "vidT3"
    vid.mkdir()
    (vid / "canonical_segments.json").write_text(
        '{"segments": [{"start": 10.0, "end": 14.0, "text": "Peace is verification."}]}',
        encoding="utf-8",
    )
    # transcript has the same sentence — corpus timings must be returned
    (transcripts_root / "vidT3.md").write_text("Peace is verification.", encoding="utf-8")
    result = tv.find_verbatim("peace is verification", "vidT3", corpus_root=tmp_path)
    assert result["status"] == "verbatim"
    assert result["start"] == 10.0 and result["end"] == 14.0
