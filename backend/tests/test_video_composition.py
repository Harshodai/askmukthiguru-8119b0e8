"""
Unit tests for Video Composition Engine & Multi-Video Synthesis (backend/services/video_composition.py).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.video_composition import (
    CompositionManifest,
    CompositionVerdict,
    FirstPersonVideoJudge,
    MediaSegment,
    VisualOverlay,
    build_composition_manifest,
    classify_segment_role,
    generate_ffmpeg_concat_filter,
    recommend_next_teachings,
    sequence_clips_by_ontology,
)


def test_classify_segment_role() -> None:
    assert classify_segment_role("Suffering is the mind's resistance to what is.") == "obstacle"
    assert classify_segment_role("When you understand the observer, you enter the beautiful state.") == "insight_shift"
    assert classify_segment_role("Let us move into meditation now. Close your eyes and inhale deeply.") == "practice_invitation"
    assert classify_segment_role("Contemplate this truth and ask yourself what is real.") == "reflection"


def test_sequence_clips_by_ontology() -> None:
    clips = [
        {"point_id": "p1", "verbatim_text": "Let us move into meditation now.", "score": 3},
        {"point_id": "p2", "verbatim_text": "Anxiety is caused by division in the mind.", "score": 3},
        {"point_id": "p3", "verbatim_text": "When you witness the thought without judging, freedom happens.", "score": 3},
    ]
    sequenced = sequence_clips_by_ontology(clips)
    roles = [classify_segment_role(c["verbatim_text"]) for c in sequenced]
    # Obstacle comes before insight, which comes before practice invitation
    assert roles == ["obstacle", "insight_shift", "practice_invitation"]
    assert sequenced[0]["point_id"] == "p2"
    assert sequenced[1]["point_id"] == "p3"
    assert sequenced[2]["point_id"] == "p1"


def test_build_composition_manifest() -> None:
    clips = [
        {
            "point_id": "pt_1",
            "video_id": "vid_abc",
            "source_url": "https://youtu.be/vid_abc",
            "audio_start_ms": 10000,
            "audio_end_ms": 25000,
            "speaker": "Sri Preethaji",
            "verbatim_text": "Suffering is self-centric thinking.",
            "speaker_verified": True,
        },
        {
            "point_id": "pt_2",
            "video_id": "vid_xyz",
            "source_url": "https://youtu.be/vid_xyz",
            "audio_start_ms": 30000,
            "audio_end_ms": 45000,
            "speaker": "Sri Krishnaji",
            "verbatim_text": "When you observe the division, peace arises.",
            "speaker_verified": True,
        },
    ]
    manifest = build_composition_manifest(
        query="What is suffering and how to find peace?",
        clips=clips,
        title="Suffering & Peace",
        modality="youtube_cards",
    )
    assert manifest.title == "Suffering & Peace"
    assert len(manifest.segments) == 2
    assert manifest.segments[0].duration_ms == 15000
    assert manifest.segments[1].duration_ms == 15000
    assert manifest.total_duration_ms == 30000
    d = manifest.to_dict()
    assert d["modality"] == "youtube_cards"
    assert len(d["segments"]) == 2


def test_generate_ffmpeg_concat_filter_multi_segment() -> None:
    manifest = CompositionManifest(
        composition_id="comp_123",
        query="How to overcome fear?",
        title="Overcoming Fear",
        segments=[
            MediaSegment(
                clip_id="c1",
                video_id="v1",
                source_url="/path/to/video1.mp4",
                start_ms=5000,
                end_ms=15000,
                speaker="Sri Preethaji",
                verbatim_text="Fear arises in the conditioned mind.",
            ),
            MediaSegment(
                clip_id="c2",
                video_id="v2",
                source_url="/path/to/video2.mp4",
                start_ms=20000,
                end_ms=35000,
                speaker="Sri Krishnaji",
                verbatim_text="Breathe deeply and witness the sensation.",
            ),
        ],
        visual_overlays=[
            VisualOverlay(
                asset_url="/path/to/soul_sync_diagram.png",
                start_ms=22000,
                end_ms=30000,
            )
        ],
        audio_crossfade_ms=50,
        output_format="mp4",
    )
    cmd = generate_ffmpeg_concat_filter(manifest, output_path="final_answer.mp4")
    assert "ffmpeg -y" in cmd
    assert "-i /path/to/video1.mp4" in cmd
    assert "-i /path/to/video2.mp4" in cmd
    assert "-i /path/to/soul_sync_diagram.png" in cmd
    assert "acrossfade=d=0.05:c1=tri:c2=tri" in cmd
    assert "scale=1920:1080" in cmd
    assert "final_answer.mp4" in cmd


@pytest.mark.asyncio
async def test_video_judge_single_clip_sufficient() -> None:
    manifest = CompositionManifest(
        composition_id="comp_single",
        query="What is love?",
        title="What is love?",
        segments=[
            MediaSegment(
                clip_id="c1",
                video_id="v1",
                source_url="https://youtu.be/v1",
                start_ms=0,
                end_ms=20000,
                speaker="Sri Preethaji",
                verbatim_text="Love is the absence of division.",
            )
        ],
    )
    judge = FirstPersonVideoJudge()
    verdict = await judge.judge_composition(manifest)
    assert verdict.is_approved is True
    assert verdict.status == "COMPOSITE_APPROVED"
    assert verdict.narrative_continuity_score == 5.0
    assert verdict.reason == "single_source_sufficient"


@pytest.mark.asyncio
async def test_video_judge_rejects_unverified_speaker() -> None:
    manifest = CompositionManifest(
        composition_id="comp_multi",
        query="What is anger?",
        title="What is anger?",
        segments=[
            MediaSegment(
                clip_id="c1",
                video_id="v1",
                source_url="https://youtu.be/v1",
                start_ms=0,
                end_ms=20000,
                speaker="Sri Preethaji",
                verbatim_text="Anger is hurt expressing itself.",
                speaker_verified=True,
            ),
            MediaSegment(
                clip_id="c2",
                video_id="v2",
                source_url="https://youtu.be/v2",
                start_ms=0,
                end_ms=20000,
                speaker="Guest",
                verbatim_text="I feel that way too.",
                speaker_verified=False,
            ),
        ],
    )
    judge = FirstPersonVideoJudge()
    verdict = await judge.judge_composition(manifest)
    assert verdict.is_approved is False
    assert verdict.status == "FALLBACK_TO_TOP_SINGLE"
    assert "unverified_speaker" in verdict.reason


@pytest.mark.asyncio
async def test_video_judge_llm_approved() -> None:
    manifest = CompositionManifest(
        composition_id="comp_llm",
        query="How to meditate?",
        title="How to meditate?",
        segments=[
            MediaSegment(
                clip_id="c1",
                video_id="v1",
                source_url="https://youtu.be/v1",
                start_ms=0,
                end_ms=10000,
                speaker="Sri Preethaji",
                verbatim_text="Meditation begins with bringing attention to the breath.",
                speaker_verified=True,
            ),
            MediaSegment(
                clip_id="c2",
                video_id="v2",
                source_url="https://youtu.be/v2",
                start_ms=0,
                end_ms=10000,
                speaker="Sri Krishnaji",
                verbatim_text="As the breath slows, the mind dissolves into stillness.",
                speaker_verified=True,
            ),
        ],
    )
    mock_llm = MagicMock()
    mock_llm.generate.return_value = json.dumps(
        {
            "narrative_continuity": 4.8,
            "transition_cleanliness": 4.5,
            "verbatim_integrity": 5.0,
            "status": "COMPOSITE_APPROVED",
            "reason": "flawless_teaching_continuity",
        }
    )
    judge = FirstPersonVideoJudge(llm_service=mock_llm)
    verdict = await judge.judge_composition(manifest)
    assert verdict.is_approved is True
    assert verdict.status == "COMPOSITE_APPROVED"
    assert verdict.narrative_continuity_score == 4.8
    assert verdict.reason == "flawless_teaching_continuity"


def test_recommend_next_teachings() -> None:
    current = [
        {"video_id": "vid_current_1", "verbatim_text": "Suffering is an inner state."}
    ]
    pool = [
        {
            "video_id": "vid_current_1",
            "title": "Current video",
            "verbatim_text": "Suffering is an inner state.",
            "score": 3.0,
        },
        {
            "video_id": "vid_next_1",
            "title": "Serene Mind Practice",
            "speaker": "Sri Krishnaji",
            "verbatim_text": "Practice this meditation every morning.",
            "score": 2.8,
        },
        {
            "video_id": "vid_next_2",
            "title": "The Four Sacred Secrets",
            "speaker": "Sri Preethaji",
            "verbatim_text": "Living in a beautiful state changes your relationships.",
            "score": 2.5,
        },
    ]
    recs = recommend_next_teachings(current, pool, limit=2)
    assert len(recs) == 2
    # Does not recommend the currently playing video
    assert "vid_current_1" not in [r["video_id"] for r in recs]
    assert recs[0]["video_id"] == "vid_next_1"
    assert recs[0]["title"] == "Serene Mind Practice"
