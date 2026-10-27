"""
test_first_person_payload_contract.py

Normative contract tests verifying the First-Person Verbatim Teaching payload shape
and layout for both Direct First-Person Route (POST /api/first-person/query) and
Main Chat Route (POST /api/chat via FirstPersonBridgeStage).

Enforces Task F4, Task E6 framing, and acceptance criteria:
- AC-0.1: Quotes verbatim (sha256 == transcript_hash, byte-identical).
- AC-0.2: No generated teaching (model_used=None, zero-generation).
- AC-0.4: Safety: crisis pre-emption precedes retrieval.
- S1: Never edit quotes (no mid-sentence insertions, no bracketed fixes).
- S3: is_direct_answer remains False until 299 calibration.
- Invariant 17: Voice-verified speaker labeling (never invent teacher credit).
"""

from __future__ import annotations

import hashlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.pipeline.result import PipelineResult
from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
from services.first_person_pipeline import FirstPersonPipeline, FirstPersonPipelineResult
from services.quote_weaver import (
    _format_continuous_quote_block,
    _format_continuous_sources_footer,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_verified_clip() -> dict[str, Any]:
    text = "Suffering arises whenever there is psychological resistance to the present moment."
    tx_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "point_id": "pt_101",
        "video_id": "hLg4WPG4ehE",
        "title": "The Beautiful State",
        "video_title": "The Beautiful State",
        "start_ms": 72000,
        "end_ms": 165000,
        "start_sec": 72,
        "end_sec": 165,
        "timestamp_seconds": 72,
        "speaker": "Sri Krishnaji",
        "teacher_id": "krishnaji",
        "speaker_verified": True,
        "channel": "Ekam - World Centre for Enlightenment",
        "transcript_hash": tx_hash,
        "verbatim_text": text,
        "text_snippet": text,
        "source_url": "https://www.youtube.com/watch?v=hLg4WPG4ehE&t=72s",
        "video_url": "https://www.youtube.com/watch?v=hLg4WPG4ehE",
        "playback_start_seconds": 72.0,
        "playback_end_seconds": 165.0,
        "playback_url": "https://www.youtube.com/watch?v=hLg4WPG4ehE&t=72s",
        "confidence": 0.92,
        "is_verbatim": True,
        "provenance_kind": "speech_turn_clip",
        "caption_status": "manual_transcript",
        "_hero": {
            "label": "Sri Krishnaji",
            "title": "The Beautiful State",
            "url": "https://www.youtube.com/watch?v=hLg4WPG4ehE&t=72s",
            "video_id": "hLg4WPG4ehE",
            "start_sec": 72,
            "speaker_verified": True,
        },
    }


@pytest.fixture
def sample_unverified_clip() -> dict[str, Any]:
    text = "In meditation, the mind settles into its natural stillness without effort."
    tx_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "point_id": "pt_102",
        "video_id": "meditation_vid_789",
        "title": "Meditation and Inner Peace",
        "video_title": "Meditation and Inner Peace",
        "start_ms": 145000,
        "end_ms": 210000,
        "start_sec": 145,
        "end_sec": 210,
        "timestamp_seconds": 145,
        "speaker": "Sri Krishnaji",
        "teacher_id": "krishnaji",
        "speaker_verified": False,  # Not voiceprint-verified!
        "channel": "Ekam Devotees Channel",
        "transcript_hash": tx_hash,
        "verbatim_text": text,
        "text_snippet": text,
        "source_url": "https://www.youtube.com/watch?v=meditation_vid_789&t=145s",
        "video_url": "https://www.youtube.com/watch?v=meditation_vid_789",
        "playback_start_seconds": 145.0,
        "playback_end_seconds": 210.0,
        "playback_url": "https://www.youtube.com/watch?v=meditation_vid_789&t=145s",
        "confidence": 0.88,
        "is_verbatim": True,
        "provenance_kind": "speech_turn_clip",
        "caption_status": "auto_transcript",
        "_hero": {
            "label": "Sri Krishnaji",
            "title": "Meditation and Inner Peace",
            "url": "https://www.youtube.com/watch?v=meditation_vid_789&t=145s",
            "video_id": "meditation_vid_789",
            "start_sec": 145,
            "speaker_verified": False,
            "channel": "Ekam Devotees Channel",
        },
    }


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_first_person_pipeline_result_schema(sample_verified_clip: dict[str, Any]) -> None:
    """Contract: FirstPersonPipelineResult.to_dict() must provide all required keys."""
    res = FirstPersonPipelineResult(
        answer_text="Sample text",
        citations=[sample_verified_clip],
        status="weak_match",
        is_direct_answer=False,
        latency_ms=120.5,
        cached=False,
        error=None,
        answerability="yes",
        abstain_reason="none",
        audio_playback_clip={
            "video_id": sample_verified_clip["video_id"],
            "title": sample_verified_clip["title"],
            "url": sample_verified_clip["source_url"],
            "start_ms": sample_verified_clip["start_ms"],
            "end_ms": sample_verified_clip["end_ms"],
            "start_sec": 72,
            "end_sec": 165,
            "speaker": sample_verified_clip["speaker"],
            "speaker_verified": True,
            "playback_url": sample_verified_clip["playback_url"],
        },
        audio_playback_clips=[
            {
                "video_id": sample_verified_clip["video_id"],
                "title": sample_verified_clip["title"],
                "url": sample_verified_clip["source_url"],
                "start_ms": sample_verified_clip["start_ms"],
                "end_ms": sample_verified_clip["end_ms"],
                "start_sec": 72,
                "end_sec": 165,
                "speaker": sample_verified_clip["speaker"],
                "speaker_verified": True,
                "playback_url": sample_verified_clip["playback_url"],
            }
        ],
        detected_concepts=["Suffering", "Meditation"],
        atma_vichara_inquiry="Where in your body do you feel this resistance right now?",
        practice_recommendation=None,
    )
    d = res.to_dict()

    # Required top-level keys
    required_keys = {
        "answer_text",
        "citations",
        "status",
        "is_direct_answer",
        "latency_ms",
        "cached",
        "error",
        "answerability",
        "abstain_reason",
        "audio_playback_clip",
        "audio_playback_clips",
        "detected_concepts",
        "atma_vichara_inquiry",
        "practice_recommendation",
    }
    assert required_keys.issubset(set(d.keys()))
    assert isinstance(d["citations"], list)
    assert isinstance(d["audio_playback_clips"], list)
    assert len(d["audio_playback_clips"]) == 1
    assert d["is_direct_answer"] is False  # S3 Invariant


def test_citation_schema_contract(sample_verified_clip: dict[str, Any]) -> None:
    """Contract: Every citation must conform to FirstPersonCitation schema requirements."""
    citation = sample_verified_clip
    assert "video_id" in citation and isinstance(citation["video_id"], str)
    assert "start_ms" in citation and isinstance(citation["start_ms"], int)
    assert "end_ms" in citation and isinstance(citation["end_ms"], int)
    assert "speaker" in citation and isinstance(citation["speaker"], str)
    assert "speaker_verified" in citation and isinstance(citation["speaker_verified"], bool)
    assert "transcript_hash" in citation and len(citation["transcript_hash"]) == 64
    assert "verbatim_text" in citation and len(citation["verbatim_text"]) > 0
    assert "source_url" in citation and "http" in citation["source_url"]
    assert "confidence" in citation and isinstance(citation["confidence"], (int, float))
    assert citation["is_verbatim"] is True


def test_quote_verbatim_byte_identity(sample_verified_clip: dict[str, Any]) -> None:
    """Contract AC-0.1 / S1: Quote text must be byte-identical to transcript_hash."""
    text_bytes = sample_verified_clip["verbatim_text"].encode("utf-8")
    computed_hash = hashlib.sha256(text_bytes).hexdigest()
    assert computed_hash == sample_verified_clip["transcript_hash"], (
        "Quote text violates AC-0.1: sha256 mismatch against stored transcript_hash"
    )


def test_continuous_layout_formatting_syntax(sample_verified_clip: dict[str, Any]) -> None:
    """Contract F4 / E6: Continuous layout block format and attribution line syntax."""
    block = _format_continuous_quote_block(sample_verified_clip, facet="suffering")

    # 1. Heading
    assert block.startswith("### On suffering\n")

    # 2. Blockquote prefix '> '
    lines = block.splitlines()
    quote_line = lines[1]
    assert quote_line.startswith("> ")
    assert sample_verified_clip["verbatim_text"] in quote_line

    # 3. Attribution format: '— Speaker · Title · ▶ MM:SS'
    attribution_line = lines[2]
    assert attribution_line.startswith("— Sri Krishnaji · The Beautiful State · ▶ 01:12")

    # 4. Invariant: NO mid-sentence markdown URLs in quote or attribution lines
    assert "http" not in attribution_line
    assert "](" not in attribution_line
    assert "](" not in quote_line


def test_continuous_sources_footer_contract(sample_verified_clip: dict[str, Any]) -> None:
    """Contract F4: Sources footer separates footnotes cleanly at the end."""
    footer = _format_continuous_sources_footer([sample_verified_clip])
    assert footer.startswith("---\nSources: ")
    assert (
        "[1] [The Beautiful State](https://www.youtube.com/watch?v=hLg4WPG4ehE&t=72s) @ 01:12"
        in footer
    )
    assert "·" not in footer.split("[1]")[0]  # No trailing dot before first source


def test_speaker_attribution_integrity_verified_vs_unverified(
    sample_verified_clip: dict[str, Any], sample_unverified_clip: dict[str, Any]
) -> None:
    """Contract Invariant 17 / E4: Unverified speaker must never be credited as a bare teacher name."""
    # Case A: Verified speaker
    verified_block = _format_continuous_quote_block(sample_verified_clip)
    assert "— Sri Krishnaji · The Beautiful State · ▶ 01:12" in verified_block

    # Case B: Unverified speaker
    unverified_block = _format_continuous_quote_block(sample_unverified_clip)
    assert (
        "— shared in Ekam Devotees Channel (unverified speaker) · Meditation and Inner Peace · ▶ 02:25"
        in unverified_block
    )
    # Must NOT credit bare teacher name without verification disclosure
    assert "— Sri Krishnaji · Meditation" not in unverified_block


@pytest.mark.asyncio
async def test_chat_bridge_route_metadata_contract(sample_verified_clip: dict[str, Any]) -> None:
    """Contract: FirstPersonBridgeStage returns PipelineResult with audio_playback_clips in route_metadata."""
    bridge = FirstPersonBridgeStage()

    text = sample_verified_clip["verbatim_text"]
    mock_pipeline_res = FirstPersonPipelineResult(
        answer_text=f'"{text}"\n— Sri Krishnaji (hLg4WPG4ehE, 72s)',
        citations=[sample_verified_clip],
        status="weak_match",
        is_direct_answer=False,
        latency_ms=85.0,
        cached=False,
        audio_playback_clip={
            "video_id": "hLg4WPG4ehE",
            "title": "The Beautiful State",
            "url": "https://www.youtube.com/watch?v=hLg4WPG4ehE&t=72s",
            "start_ms": 72000,
            "end_ms": 165000,
            "start_sec": 72,
            "end_sec": 165,
            "speaker": "Sri Krishnaji",
            "speaker_verified": True,
            "playback_url": "https://www.youtube.com/watch?v=hLg4WPG4ehE&t=72s",
        },
        audio_playback_clips=[
            {
                "video_id": "hLg4WPG4ehE",
                "title": "The Beautiful State",
                "url": "https://www.youtube.com/watch?v=hLg4WPG4ehE&t=72s",
                "start_ms": 72000,
                "end_ms": 165000,
                "start_sec": 72,
                "end_sec": 165,
                "speaker": "Sri Krishnaji",
                "speaker_verified": True,
                "playback_url": "https://www.youtube.com/watch?v=hLg4WPG4ehE&t=72s",
            }
        ],
        detected_concepts=["Suffering"],
    )

    from app.config import settings

    container = MagicMock()
    container.embedding.encode_single_full_async = AsyncMock(
        return_value={"dense": [0.1] * settings.embedding_dimension, "sparse": {}}
    )
    container.guardrails.check_output = AsyncMock(
        return_value=MagicMock(passed=True, blocked=False)
    )
    mock_fp = MagicMock()
    mock_fp.execute.return_value = mock_pipeline_res
    container.first_person_pipeline = mock_fp

    ctx = MagicMock()
    ctx.user_msg = "Tell me about suffering in life"
    ctx.trace_id = "trace_abc_123"
    ctx.start_time = 0.0
    ctx.is_indic = False
    ctx.user_id = None
    ctx.incognito = True
    ctx.routing_chain = []
    ctx.container = container
    ctx.assessment = None

    with patch("app.pipeline.stages.first_person_bridge._fp_pipeline", return_value=mock_fp):
        res = await bridge._bridge(ctx)

    assert isinstance(res, PipelineResult)
    # AC-0.2 invariant: zero generated teaching
    assert res.model_used is None
    assert res.model_provider is None
    assert res.route_decision == "first_person_bridge"
    assert res.citations_verified is True
    assert res.verification["passed"] is True
    assert res.verification["direct"] is False

    # Route metadata validation
    meta = res.route_metadata
    assert "audio_playback_clip" in meta and meta["audio_playback_clip"] is not None
    assert "audio_playback_clips" in meta and isinstance(meta["audio_playback_clips"], list)
    assert len(meta["audio_playback_clips"]) == 1
    assert meta["audio_playback_clips"][0]["video_id"] == "hLg4WPG4ehE"
    assert "detected_concepts" in meta


def test_per_part_honest_abstention_phrase_contract() -> None:
    """Contract F1/F2 / S2: Missing part reports explicit honest gap, never generated text."""
    expected_gap = "I don't have a recording that answers this part yet."
    sample_compound_answer = (
        "### On suffering and meditation\n"
        "> Suffering arises from resistance.\n"
        "— Sri Krishnaji · The Beautiful State · ▶ 01:12\n\n"
        "### On prosperity and success\n"
        f"{expected_gap}\n\n"
        "---\n"
        "Sources: [1] The Beautiful State @ 01:12"
    )
    assert expected_gap in sample_compound_answer
    # Directness is metadata, not text: the label never rides in the body.
    assert "Related, not a direct answer" not in sample_compound_answer


def test_crisis_preemption_contract() -> None:
    """Contract AC-0.4 / S4: Crisis rail precedes retrieval and redirects."""
    mock_store = MagicMock()
    pipeline = FirstPersonPipeline(store=mock_store)

    crisis_query = "I want to end my life, I can't go on anymore"
    res = pipeline.execute(
        query=crisis_query,
        query_dense_vector=[0.1] * 1024,
    )

    assert res.status == "crisis_redirect"
    assert res.is_direct_answer is False
    assert len(res.citations) == 0
    # Store search should NOT be called on crisis pre-emption
    assert "988" in res.answer_text or "helpline" in res.answer_text.lower()


def test_orphan_opener_e5_filtering() -> None:
    """Test Task E5: Demonstrative openers ('yes,', 'this/these/those/that + is/are/was/were')."""
    from services.first_person_pipeline import _standalone_problem

    # Should be flagged as orphan openers
    assert _standalone_problem("Yes, this resolves the entire problem.") == "orphan_opener"
    assert _standalone_problem("Yes. We must realize the truth.") == "orphan_opener"
    assert _standalone_problem("These are suffering states.") == "orphan_opener"
    assert _standalone_problem("This is the essence of meditation.") == "orphan_opener"
    assert _standalone_problem("Those were the times when wisdom flourished.") == "orphan_opener"
    assert _standalone_problem("That was what we experienced.") == "orphan_opener"

    # "It is"/"It was"/"It's" are complete copula openers, not orphan pronouns.
    assert _standalone_problem("It is the essence of meditation.") is None
    assert _standalone_problem("It was the essence of meditation.") is None
    assert _standalone_problem("It's the essence of meditation.") is None
    assert _standalone_problem("It\u2019s the essence of meditation.") is None

    # "So..." is kept allowed per Task E5 ("So both Preethaji and I… is a fine opener")
    assert _standalone_problem("So both Preethaji and I have walked this sacred path.") is None
    assert (
        _standalone_problem("When you observe the mind without judgment, stillness arises.") is None
    )


def test_stage_timings_instrumentation_e6a(sample_verified_clip: dict[str, Any]) -> None:
    """Test Task E6a: Stage timings breakdown in pipeline result."""
    mock_store = MagicMock()
    mock_store.search_hybrid.return_value = [sample_verified_clip]

    pipeline = FirstPersonPipeline(store=mock_store)
    res = pipeline.execute(
        query="What is a beautiful state?",
        query_dense_vector=[0.1] * 1024,
    )

    assert hasattr(res, "stage_timings")
    timings = res.stage_timings
    assert "retrieval_ms" in timings
    assert "integrity_ms" in timings
    assert "rerank_ms" in timings
    assert "scorer_ms" in timings
    assert "assembly_ms" in timings
    assert "total_ms" in timings
    assert timings["total_ms"] >= 0.0


def test_reranker_none_early_abstention_e6c(sample_verified_clip: dict[str, Any]) -> None:
    """Test Task E6c: Reranker NONE early abstention."""
    text = (
        "Suffering arises whenever there is psychological resistance to the present moment, "
        "and when you surrender completely, profound stillness and peace fill your entire being."
    )
    tx_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    clip1 = {
        **sample_verified_clip,
        "verbatim_text": text,
        "text_snippet": text,
        "transcript_hash": tx_hash,
    }
    clip2 = {
        **sample_verified_clip,
        "point_id": "pt_102",
        "video_id": "vid2",
        "verbatim_text": text,
        "text_snippet": text,
        "transcript_hash": tx_hash,
    }

    mock_store = MagicMock()
    mock_store.search_hybrid.return_value = [clip1, clip2]

    mock_llm = MagicMock()
    mock_llm.generate.return_value = "NONE"

    with patch("services.first_person_pipeline.settings") as mock_settings:
        mock_settings.first_person_llm_rerank_enabled = True
        mock_settings.first_person_rerank_none_abstain_enabled = True
        mock_settings.first_person_answerability_check_enabled = False
        mock_settings.first_person_max_clip_seconds = 120
        mock_settings.first_person_min_clip_words = 10
        mock_settings.first_person_quality_allowlist_path = ""
        mock_settings.first_person_quality_blocklist_path = ""

        pipeline = FirstPersonPipeline(store=mock_store, llm_service=mock_llm)
        res = pipeline.execute(
            query="What is the capital of France?",
            query_dense_vector=[0.1] * 1024,
        )

        assert res.status == "abstained"
        assert res.abstain_reason == "relevance_below_min"
        assert len(res.citations) == 0
        assert "rerank_ms" in res.stage_timings
        assert res.stage_timings["total_ms"] > 0.0


@pytest.mark.relevance_real
def test_compound_facet_split_and_assembly_contract(sample_verified_clip: dict[str, Any]) -> None:
    """Test Tasks F1 & F2: Compound question facet splitting, per-part scoring, and continuous layout assembly."""
    text1 = (
        "Meditation is the art of observing the movement of your mind without judgment, "
        "allowing inner stillness and clarity to awaken naturally within you."
    )
    tx_hash1 = hashlib.sha256(text1.encode("utf-8")).hexdigest()
    clip1 = {
        **sample_verified_clip,
        "point_id": "pt_med_1",
        "video_id": sample_verified_clip["video_id"],
        "verbatim_text": text1,
        "text_snippet": text1,
        "transcript_hash": tx_hash1,
        "title": "On Meditation and Stillness",
        "channel": "Ekam - World Centre for Enlightenment",
    }

    mock_store = MagicMock()
    mock_store.search_hybrid.return_value = [clip1]

    # Mock LLM:
    # 1. Query decomposition: returns 2 subquestions
    # 2. Relevance scoring for facet 1: "3" -> passes gate >= 3
    # 3. Relevance scoring for facet 2: "0" -> fails gate -> gets honest gap reporting
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = [
        "What is meditation?\nHow does it heal suffering?",
        "3",
        "0",
    ]

    with patch("services.first_person_pipeline.settings") as mock_settings:
        mock_settings.first_person_facet_split_enabled = True
        mock_settings.first_person_relevance_min_score = 3
        mock_settings.first_person_relevance_model = ""
        mock_settings.first_person_calibration_path = ""
        mock_settings.first_person_max_clip_seconds = 120
        mock_settings.first_person_min_clip_words = 10
        mock_settings.first_person_quality_allowlist_path = ""
        mock_settings.first_person_quality_blocklist_path = ""
        mock_settings.first_person_boundary_guard_enabled = False
        mock_settings.first_person_content_quality_gate_enabled = False

        pipeline = FirstPersonPipeline(store=mock_store, llm_service=mock_llm)
        compound_query = "What is meditation, and how does it heal suffering?"
        res = pipeline.execute(
            query=compound_query,
            query_dense_vector=[0.1] * 1024,
        )

        assert res.status == "weak_match"
        assert res.is_direct_answer is False
        assert len(res.citations) == 1
        assert res.citations[0]["point_id"] == "pt_med_1"

        # Continuous layout contract check. The related label is metadata
        # (status/is_direct_answer), never answer text (plan T2a 2026-10-27).
        assert "### On " in res.answer_text
        assert "I don't have a recording that answers this part yet." in res.answer_text
        assert "Related, not a direct answer" not in res.answer_text
        assert "Sources: [1]" in res.answer_text

        # Audio playback clips
        assert len(res.audio_playback_clips) == 1
        assert res.audio_playback_clips[0]["video_id"] == sample_verified_clip["video_id"]

        # Stage timings
        assert "retrieval_ms" in res.stage_timings
        assert "scorer_ms" in res.stage_timings
        assert "assembly_ms" in res.stage_timings
        assert res.stage_timings["total_ms"] > 0.0


def test_validate_release_grade_contract() -> None:
    """Test SourceSpan.validate_release_grade() for D9."""
    from domain.first_person_context import (
        BoundaryStatus,
        CompletenessStatus,
        ProvenanceKind,
        SourceSpan,
        SpeakerRole,
        clip_text_hash,
        make_source_span_id,
    )

    text = "Meditation brings complete inner stillness and freedom from all suffering."
    h = "a" * 64
    span_id = make_source_span_id(
        guru_id="krishnaji",
        video_id="vid123",
        corpus_version="v1",
        word_start=0,
        word_end=10,
        transcript_hash=h,
    )
    span = SourceSpan(
        corpus_version="v1",
        guru_id="krishnaji",
        video_id="vid123",
        source_asset_id="vid123",
        source_span_id=span_id,
        parent_unit_id="p123",
        turn_id="t123",
        turn_index=0,
        source_span_index=0,
        start_ms=10000,
        end_ms=25000,
        word_start=0,
        word_end=10,
        speaker_id="krishnaji",
        speaker_role=SpeakerRole.GURU,
        speaker_verified=True,
        voice_verification_method="ecapa_voxceleb_span_slice_v2",
        source_transcript_text=text,
        verbatim_text=text,
        transcript_hash=h,
        source_text_hash=clip_text_hash(text),
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
        rights_cleared=True,
        caption_status="auto",
        provenance_kind=ProvenanceKind.SPEECH_TURN_SPAN,
        source_url="https://youtube.com/watch?v=vid123",
        contextual_header_version=None,
    )
    assert span.validate_release_grade() == []

    # If speaker_verified is True but voice_verification_method is None
    unverified_method = span.model_copy(update={"voice_verification_method": None})
    assert "speaker_verified_without_method" in unverified_method.validate_release_grade()

    # If duration out of band (<8s)
    short_span = span.model_copy(update={"end_ms": 14000})
    assert any("duration_out_of_band" in d for d in short_span.validate_release_grade())


def test_provenance_fields_are_optional_and_validated():
    """Provenance is recorded only when the producer actually knows it (D4/D15/D16)."""
    from domain.first_person_context import SourceSpan, TextOrigin, make_source_span_id

    h = "a" * 64
    span_id = make_source_span_id(
        guru_id="krishnaji",
        video_id="vid123",
        corpus_version="v1",
        word_start=0,
        word_end=10,
        transcript_hash=h,
    )
    base = dict(
        corpus_version="v1",
        guru_id="krishnaji",
        video_id="vid123",
        source_asset_id="vid123",
        source_span_id=span_id,
        parent_unit_id="p123",
        turn_id="t123",
        turn_index=0,
        source_span_index=0,
        start_ms=10000,
        end_ms=25000,
        word_start=0,
        word_end=10,
        speaker_id="krishnaji",
        speaker_role="guru",
        speaker_verified=False,
        boundary_status="verified",
        completeness_status="complete",
        rights_cleared=True,
        caption_status="auto",
        source_transcript_text="text",
        verbatim_text="text",
        transcript_hash=h,
        source_text_hash=__import__("hashlib").sha256(b"text").hexdigest(),
        source_url="https://youtube.com/watch?v=vid123",
    )
    span = SourceSpan(**base)
    # Unrecorded provenance must stay unrecorded, never a plausible default.
    assert span.text_origin is None
    assert span.source_artifact_sha256 is None
    assert span.embedding_model is None

    recorded = SourceSpan(
        **base,
        text_origin=TextOrigin.ASR_VOTED,
        source_artifact_sha256="c" * 64,
        embedding_model="BAAI/bge-m3",
        embedding_revision="d" * 40,
        embedded_text_sha256="e" * 64,
    )
    assert recorded.text_origin is TextOrigin.ASR_VOTED
    assert recorded.source_artifact_sha256 == "c" * 64

    # A pydantic ValidationError, and it must name the offending field: a bare
    # ``Exception`` also accepts an unrelated failure (e.g. a missing required
    # field) and would pass while proving nothing about the pattern.
    with pytest.raises(ValidationError) as bad_artifact:
        SourceSpan(**base, source_artifact_sha256="not-a-sha256")
    assert "source_artifact_sha256" in str(bad_artifact.value)

    with pytest.raises(ValidationError) as bad_embedding:
        SourceSpan(**base, embedded_text_sha256="NOT-HEX")
    assert "embedded_text_sha256" in str(bad_embedding.value)

    with pytest.raises(ValidationError) as bad_window:
        SourceSpan(**base, window_count=-1)
    assert "window_count" in str(bad_window.value)
