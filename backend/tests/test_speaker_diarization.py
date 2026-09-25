"""Unit tests for Speaker Diarization & Quotable Clip Pipeline (Invariants C1/C2/C3)."""

import pytest
from services.speaker_diarization import (
    compute_clip_hash,
    apply_speaker_attribution_to_segments,
    extract_quotable_clips,
)


def test_compute_clip_hash_deterministic():
    text = "Suffering ends when you cease to divide yourself from life."
    h1 = compute_clip_hash(text)
    h2 = compute_clip_hash(text)
    assert h1 == h2
    assert len(h1) == 64


def test_compute_clip_hash_matches_exact_string_no_normalization():
    """compute_clip_hash must hash the exact verbatim_text it is given -- no
    internal whitespace normalization. Callers (the clip builder, the serving
    check) join segment texts with a single space themselves; a second,
    diverging normalization inside compute_clip_hash would make their hashes
    disagree."""
    import hashlib

    text = "Fear is the projection of the past into an imagined future."
    assert compute_clip_hash(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()
    # Leading/trailing whitespace changes the exact string -> a different hash.
    assert compute_clip_hash(text) != compute_clip_hash(f"  {text}  ")


def test_apply_speaker_attribution_to_segments():
    segments = [
        {"segment_id": "s0", "start": 0.0, "end": 4.0, "text": "Can you explain the beautiful state?"},
        {"segment_id": "s1", "start": 5.0, "end": 12.0, "text": "The beautiful state is our natural interconnected presence."},
    ]
    speaker_windows = [
        {"t_start": 0.0, "t_end": 4.0, "speaker": "O"},  # Host/Questioner
        {"t_start": 5.0, "t_end": 12.0, "speaker": "P"},  # Sri Preethaji
    ]

    updated = apply_speaker_attribution_to_segments(segments, speaker_windows)
    assert len(updated) == 2

    # Segment 0: Questioner
    assert updated[0]["speaker_evidence"]["speaker_role"] == "questioner"
    assert updated[0]["speaker_evidence"]["detected_speaker"] == "Host / Questioner"

    # Segment 1: Teacher
    assert updated[1]["speaker_evidence"]["speaker_role"] == "teacher"
    assert updated[1]["speaker_evidence"]["detected_speaker"] == "Sri Preethaji"


def test_extract_quotable_clips_excludes_host_and_pads():
    segments = [
        {
            "segment_id": "s0",
            "start": 0.0,
            "end": 2.0,
            "text": "What is fear?",
            "speaker_evidence": {"speaker_role": "questioner", "detected_speaker": "Host / Questioner"},
        },
        {
            "segment_id": "s1",
            "start": 3.0,
            "end": 8.0,
            "text": "Fear is the projection of the past into an imagined future.",
            "verbatim_text": "Fear is the projection of the past into an imagined future.",
            "speaker_evidence": {"speaker_role": "teacher", "detected_speaker": "Sri Krishnaji"},
        },
        {
            "segment_id": "s2",
            "start": 8.5,
            "end": 12.0,
            "text": "When you observe it completely, it dissolves into stillness.",
            "verbatim_text": "When you observe it completely, it dissolves into stillness.",
            "speaker_evidence": {"speaker_role": "teacher", "detected_speaker": "Sri Krishnaji"},
        },
    ]

    clips = extract_quotable_clips(segments, video_id="vid_test_123", padding_s=0.20)
    # Host segment is excluded; teacher segments s1 and s2 are grouped into 1 clip
    assert len(clips) == 1
    clip = clips[0]
    assert clip["speaker"] == "Sri Krishnaji"
    assert clip["video_id"] == "vid_test_123"
    assert clip["start"] == 2.8  # 3.0 - 0.20
    assert clip["end"] == 12.2   # 12.0 + 0.20
    assert "Fear is the projection" in clip["verbatim_text"]
    assert "dissolves into stillness" in clip["verbatim_text"]
    assert len(clip["transcript_hash"]) == 64


def test_extract_quotable_clips_splits_long_run_at_largest_gaps():
    """A single teacher run longer than max_duration_s must be split at its
    internal gaps rather than dropped entirely -- teachers speak uninterrupted
    for minutes and that speech must not be lost. Every segment must end up
    in exactly one clip (no overlap, no omission)."""
    starts_ends = [
        (0.0, 9.7), (9.8, 19.5), (19.6, 29.3), (29.4, 39.1), (39.2, 48.9),
        (53.9, 63.6), (63.7, 73.4), (73.5, 83.2), (83.3, 93.0), (93.1, 102.8),
        (107.8, 117.5), (117.6, 127.3), (127.4, 137.1), (137.2, 146.9), (147.0, 156.7),
    ]
    segments = []
    for i, (s, e) in enumerate(starts_ends):
        text = f"Segment number {i} of the teaching on stillness."
        segments.append(
            {
                "segment_id": f"s{i}",
                "start": s,
                "end": e,
                "text": text,
                "verbatim_text": text,
                "speaker_evidence": {"speaker_role": "teacher", "detected_speaker": "Sri Krishnaji"},
            }
        )

    clips = extract_quotable_clips(segments, video_id="vid_long", padding_s=0.20)

    assert len(clips) >= 3
    for clip in clips:
        assert clip["duration_seconds"] <= 60.0
        assert clip["transcript_hash"] == compute_clip_hash(clip["verbatim_text"])

    # Every segment's text appears in exactly one clip -- no overlap, no omission.
    for seg in segments:
        containing = [c for c in clips if seg["text"] in c["verbatim_text"]]
        assert len(containing) == 1, f"segment {seg['segment_id']} appeared in {len(containing)} clips"

    total_words_in_clips = sum(len(c["verbatim_text"].split()) for c in clips)
    total_words_in_segments = sum(len(seg["text"].split()) for seg in segments)
    assert total_words_in_clips == total_words_in_segments


def test_single_segment_longer_than_max_is_kept_not_dropped():
    """A split can't go below one segment; an unsplittable 90 s teacher segment
    must still become a clip -- dropping it is the silent loss the split fixed."""
    from services.speaker_diarization import extract_quotable_clips

    seg = {"start": 0.0, "end": 90.0, "text": "one long uninterrupted teaching",
           "speaker_evidence": {"speaker_role": "teacher", "detected_speaker": "Sri Krishnaji"}}
    clips = extract_quotable_clips([seg], video_id="v1", max_duration_s=60.0)
    assert len(clips) == 1 and clips[0]["verbatim_text"] == "one long uninterrupted teaching"
