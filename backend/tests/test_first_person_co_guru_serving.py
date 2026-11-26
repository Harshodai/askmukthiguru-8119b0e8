"""Tests for co-guru founder context hydration, speaker gate, and sub-10s latency guards."""

from unittest.mock import AsyncMock, patch

import pytest

from domain.first_person_context import (
    BoundaryStatus,
    CompletenessStatus,
    ParentContext,
    ParentUnit,
    ProvenanceKind,
    SourceSpan,
    SpeakerRole,
    _is_same_or_shared_guru,
    clip_text_hash,
    make_source_span_id,
)
from rag.nodes.reranking import _limit_rerank_candidates
from services.first_person_context_harness import (
    FirstPersonContextHarness,
    HarnessPolicy,
)
from services.first_person_context_store import (
    FirstPersonContextStore,
    FirstPersonContextStoreError,
)


def _dummy_span(
    span_id: str = "s1",
    parent_id: str = "p1",
    guru_id: str = "preethaji",
    role: SpeakerRole = SpeakerRole.TEACHER,
    **overrides,
) -> SourceSpan:
    text = "The four sacred secrets lead to a life of inner freedom."
    span_index = overrides.pop("source_span_index", 0 if span_id == "s1" else abs(hash(span_id)) % 1000 + 1)
    word_start = overrides.pop("word_start", span_index * 10)
    word_end = overrides.pop("word_end", word_start + 10)
    corpus_version = overrides.get("corpus_version", "fp-context-v1")
    video_id = overrides.get("video_id", "vid_test_123")
    thash = overrides.get("transcript_hash", "a" * 64)
    deterministic_id = make_source_span_id(
        guru_id=guru_id,
        video_id=video_id,
        corpus_version=corpus_version,
        word_start=word_start,
        word_end=word_end,
        transcript_hash=thash,
    )
    data = {
        "source_span_id": deterministic_id,
        "source_asset_id": "asset_123",
        "parent_unit_id": parent_id,
        "corpus_version": corpus_version,
        "video_id": video_id,
        "guru_id": guru_id,
        "turn_id": "turn_001",
        "turn_index": span_index,
        "source_span_index": span_index,
        "start_ms": 1000 + span_index * 1000,
        "end_ms": 30000 + span_index * 1000,
        "word_start": word_start,
        "word_end": word_end,
        "speaker_id": guru_id,
        "speaker_role": role,
        "speaker_verified": True,
        "voice_verification_method": "ecapa_voxceleb_span_slice_v2",
        "voice_model_revision": "rev-test",
        "voice_score": 0.71,
        "voice_margin": 0.40,
        "voice_threshold_applied": {"cosine_floor": 0.2828, "margin_threshold": 0.05},
        "voice_calibration_id": "cal-test",
        "voice_window_check": "pass",
        "voice_verified_at": "2026-10-31T00:00:00+00:00",
        "speaker_verification_status": "verified",
        "source_transcript_text": text,
        "verbatim_text": text,
        "transcript_hash": thash,
        "source_text_hash": clip_text_hash(text),
        "boundary_status": BoundaryStatus.VERIFIED,
        "completeness_status": CompletenessStatus.COMPLETE,
        "rights_cleared": True,
        "domain_rights_status": "licensed",
        "caption_status": "auto",
        "provenance_kind": ProvenanceKind.SPEECH_TURN_SPAN,
        "source_url": "https://www.youtube.com/watch?v=vid_test_123",
    }
    data.update(overrides)
    return SourceSpan(**data)


def _dummy_parent(spans: tuple[SourceSpan, ...], guru_id: str = "krishnaji", **overrides) -> ParentUnit:
    data = {
        "corpus_version": "fp-context-v1",
        "guru_id": guru_id,
        "video_id": spans[0].video_id,
        "parent_unit_id": spans[0].parent_unit_id,
        "ordered_source_span_ids": tuple(s.source_span_id for s in spans),
        "start_ms": spans[0].start_ms,
        "end_ms": spans[-1].end_ms,
        "parent_text_hash": clip_text_hash(" ".join(s.verbatim_text for s in spans)),
        "speaker_ids": (guru_id,),
        "speaker_continuity": True,
        "boundary_status": BoundaryStatus.VERIFIED,
        "completeness_status": CompletenessStatus.COMPLETE,
    }
    data.update(overrides)
    return ParentUnit(**data)


def test_is_same_or_shared_guru():
    """Verify co-guru founders match across raw and prefixed variants."""
    assert _is_same_or_shared_guru("krishnaji", "krishnaji") is True
    assert _is_same_or_shared_guru("krishnaji", "preethaji") is True
    assert _is_same_or_shared_guru("sri_krishnaji", "sri_preethaji") is True
    assert _is_same_or_shared_guru("sri-krishnaji", "preethaji") is True
    assert _is_same_or_shared_guru("krishnaji", "sadhguru") is False
    assert _is_same_or_shared_guru("preethaji", "osho") is False
    assert _is_same_or_shared_guru(None, "krishnaji") is False


def test_context_store_assert_belongs_co_guru():
    """Store must accept spans from co-guru founder in a joint parent context."""
    s1 = _dummy_span(span_id="s1", parent_id="p1", guru_id="preethaji")
    parent = _dummy_parent((s1,), guru_id="krishnaji")

    # Co-guru span should not raise
    FirstPersonContextStore._assert_belongs(parent, s1)

    # Foreign guru must raise
    span_foreign = _dummy_span(span_id="s2", parent_id="p1", guru_id="unregistered_guest")
    with pytest.raises(FirstPersonContextStoreError, match="span guru_id differs from parent"):
        FirstPersonContextStore._assert_belongs(parent, span_foreign)


def test_parent_context_pydantic_co_guru_validation():
    """ParentContext model validation permits co-guru spans."""
    s1 = _dummy_span(span_id="s1", parent_id="p1", guru_id="krishnaji")
    s2 = _dummy_span(span_id="s2", parent_id="p1", guru_id="preethaji")
    parent = _dummy_parent((s1, s2), guru_id="krishnaji")

    ctx = ParentContext(parent=parent, spans=(s1, s2), hit_span_ids=(s1.source_span_id,))
    assert len(ctx.spans) == 2
    assert ctx.parent.guru_id == "krishnaji"


def test_speaker_gate_accepts_teacher_and_guru_roles():
    """Harness speaker gate accepts GURU and TEACHER speaker roles."""
    harness = FirstPersonContextHarness()
    policy = HarnessPolicy(require_speaker_verified=True)

    span_teacher = _dummy_span(span_id="s1", guru_id="krishnaji", role=SpeakerRole.TEACHER)
    span_guru = _dummy_span(span_id="s2", guru_id="preethaji", role=SpeakerRole.GURU)

    assert harness._speaker_gate((span_teacher, span_guru), policy) is True

    span_host = _dummy_span(span_id="s3", guru_id="krishnaji", role=SpeakerRole.HOST)
    assert harness._speaker_gate((span_teacher, span_host), policy) is False


def test_rerank_candidates_cap_standard_tier(monkeypatch):
    """_limit_rerank_candidates bounds standard tier to 10 candidates."""
    from app.config import settings

    monkeypatch.setattr(settings, "rag_quantized_reranker_enabled", False)
    docs = [{"id": i, "score": 1.0 - i * 0.05} for i in range(20)]
    capped = _limit_rerank_candidates(docs, "standard")
    assert len(capped) == 10
    assert capped[0]["id"] == 0
    assert capped[9]["id"] == 9

    # tier2_simple capped to 8
    capped_simple = _limit_rerank_candidates(docs, "tier2_simple")
    assert len(capped_simple) == 8


@pytest.mark.asyncio
async def test_openrouter_generate_fast_operation_kwarg():
    """_generate_fast must accept operation in kwargs without throwing multiple values error."""
    from services.openrouter_service import OpenRouterService

    service = OpenRouterService()
    with patch.object(service, "_call_api", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = "Hypothetical document content"
        res = await service._generate_fast(
            system_prompt="sys",
            user_prompt="usr",
            operation="generate_hyde",
            temperature=0.7,
        )
        assert res == "Hypothetical document content"
        mock_call.assert_called_once()
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs["operation"] == "generate_hyde"
        assert call_kwargs["temperature"] == 0.7
