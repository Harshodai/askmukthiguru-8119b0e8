"""Writer contract test for first-person span hash semantics (DATA-03 / T3-03).

In vNext (schema fp-context-v2):
- `video_transcript_sha256` represents the SHA-256 of the whole video verbatim transcript.
- `span_text_sha256` represents the SHA-256 of the span's verbatim text.
- Every writer must satisfy: span hash == sha256(verbatim_text).
"""

from __future__ import annotations

import hashlib

import pytest

from domain.first_person_context import (
    SCHEMA_VERSION_V2,
    BoundaryStatus,
    CompletenessStatus,
    SourceSpan,
    SpeakerRole,
    make_source_span_id,
)
from domain.hash_fields import (
    compute_span_text_sha256,
    resolve_span_text_sha256,
    resolve_video_transcript_sha256,
)
from services.first_person_store import validate_clip_entry


@pytest.mark.parametrize(
    "verbatim_text",
    [
        "When you are in a beautiful state, life is beautiful.",
        "Suffering is a choice. You can step out of suffering right now.",
        "Meditation is silence of the mind.",
    ],
)
def test_hash_fields_helpers(verbatim_text: str):
    """compute_span_text_sha256 matches sha256(verbatim_text.encode('utf-8'))."""
    expected = hashlib.sha256(verbatim_text.encode("utf-8")).hexdigest()
    assert compute_span_text_sha256(verbatim_text) == expected


def test_source_span_v2_writer_contract():
    """SourceSpan in fp-context-v2 enforces span_text_sha256 and video_transcript_sha256."""
    text = "Awareness dissolves all division."
    span_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    video_hash = hashlib.sha256(b"Full transcript text").hexdigest()

    span_id = make_source_span_id(
        guru_id="krishnaji",
        video_id="vid_001",
        corpus_version="v2",
        word_start=0,
        word_end=4,
        video_transcript_sha256=video_hash,
    )

    span = SourceSpan(
        schema_version=SCHEMA_VERSION_V2,
        corpus_version="v2",
        guru_id="krishnaji",
        video_id="vid_001",
        source_asset_id="vid_001",
        source_span_id=span_id,
        parent_unit_id="parent_001",
        turn_id="turn_001",
        turn_index=0,
        source_span_index=0,
        start_ms=0,
        end_ms=2500,
        word_start=0,
        word_end=4,
        speaker_id="krishnaji",
        speaker_role=SpeakerRole.GURU,
        speaker_verified=True,
        source_transcript_text=text,
        verbatim_text=text,
        span_text_sha256=span_hash,
        video_transcript_sha256=video_hash,
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
        rights_cleared=True,
        caption_status="auto",
        source_url="https://youtube.com/watch?v=vid_001",
    )

    payload = span.to_payload()
    assert payload["span_text_sha256"] == span_hash
    assert payload["video_transcript_sha256"] == video_hash
    assert resolve_span_text_sha256(payload) == span_hash
    assert resolve_video_transcript_sha256(payload) == video_hash


def test_source_span_v2_refuses_span_hash_mismatch():
    """SourceSpan rejects payload if span_text_sha256 does not match verbatim_text."""
    text = "Awareness dissolves all division."
    wrong_hash = hashlib.sha256(b"Tampered text").hexdigest()
    video_hash = hashlib.sha256(b"Full transcript text").hexdigest()

    span_id = make_source_span_id(
        guru_id="krishnaji",
        video_id="vid_001",
        corpus_version="v2",
        word_start=0,
        word_end=4,
        video_transcript_sha256=video_hash,
    )

    with pytest.raises(ValueError, match="span_text_sha256"):
        SourceSpan(
            schema_version=SCHEMA_VERSION_V2,
            corpus_version="v2",
            guru_id="krishnaji",
            video_id="vid_001",
            source_asset_id="vid_001",
            source_span_id=span_id,
            parent_unit_id="parent_001",
            turn_id="turn_001",
            turn_index=0,
            source_span_index=0,
            start_ms=0,
            end_ms=2500,
            word_start=0,
            word_end=4,
            speaker_id="krishnaji",
            speaker_role=SpeakerRole.GURU,
            speaker_verified=True,
            source_transcript_text=text,
            verbatim_text=text,
            span_text_sha256=wrong_hash,  # Mismatched!
            video_transcript_sha256=video_hash,
            boundary_status=BoundaryStatus.VERIFIED,
            completeness_status=CompletenessStatus.COMPLETE,
            rights_cleared=True,
            caption_status="auto",
            source_url="https://youtube.com/watch?v=vid_001",
        )


def test_validate_clip_entry_accepts_span_text_sha256():
    """Legacy/v1 store validation accepts span_text_sha256 in lieu of transcript_hash."""
    text = "Peace is your natural state."
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()

    clip = {
        "video_id": "v123",
        "start_ms": 1000,
        "end_ms": 5000,
        "speaker": "Sri Krishnaji",
        "verbatim_text": text,
        "span_text_sha256": h,
    }
    # Should validate cleanly without raising
    validate_clip_entry(clip)
