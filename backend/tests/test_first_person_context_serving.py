"""Serving integration tests for the First-Person Context Harness in FirstPersonPipeline.

Validates that:
1. When first_person_context_harness_enabled is True and first_person_context_collection is set:
   - FirstPersonContextStore and FirstPersonContextHarness are used to retrieve and decide.
   - Decisions for serve_single_span and serve_parent_context construct FirstPersonPipelineResult
     with status='success' and deterministically reconstructed text; is_direct_answer follows the
     same calibrated-profile rule as the legacy path (no profile = related, never direct).
   - Citations point to exact video ID, start_ms, end_ms, and title.
   - Audio playback clips are correctly built.
2. Invariants:
   - answer_text is NEVER authored or modified by an LLM.
   - When harness abstains, store returns empty, or store errors: falls back gracefully to legacy.
   - When harness flag is False, context harness is not invoked.
   - Exact caching works with context harness results.
   - Selector integration honors selected span IDs and fails open on unexpected output.
3. Live Qdrant integration against fp_context_v1_local.
"""

from __future__ import annotations

import hashlib
import json
from unittest.mock import Mock, patch

import pytest
from qdrant_client import QdrantClient

from app.config import settings
from domain.first_person_context import (
    _VALIDATED_EDGE_ISSUE_TOKEN,
    AnswerRole,
    BoundaryStatus,
    CompletenessStatus,
    ParentContext,
    ParentUnit,
    ProvenanceKind,
    SourceSpan,
    SpeakerRole,
    ValidatedCrossParentEdge,
    clip_text_hash,
    make_source_span_id,
)
from services.first_person_context_harness import (
    FirstPersonContextHarness,
    reset_harness_metrics,
)
from services.first_person_pipeline import FirstPersonPipeline, _relevance_select_scored

TEXT_ONE = (
    "Suffering is not a punishment that existence hands to you; it is a call to awaken "
    "to the resistance you carry inside yourself every single day."
)
TEXT_TWO = (
    "When you stop fighting that pain and simply stay present with it, the mind becomes "
    "quiet and the heart opens without any effort at all."
)


@pytest.fixture(autouse=True)
def _synthetic_rights_register(monkeypatch):
    for target in (
        "services.first_person_context_harness.source_is_authoritatively_licensed",
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        "services.first_person_context_store.source_is_authoritatively_licensed",
    ):
        monkeypatch.setattr(
            target,
            lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
        )


def make_test_span(n: int = 0, text: str | None = None, **overrides) -> SourceSpan:
    span_text = text or (TEXT_ONE if n == 0 else TEXT_TWO)
    word_start = overrides.pop("word_start", n * 10)
    word_end = overrides.pop("word_end", word_start + 6)
    parent_unit_id = overrides.pop("parent_unit_id", "parent_101")
    video_id = overrides.pop("video_id", "vid_test_1")
    guru_id = overrides.pop("guru_id", "krishnaji")
    # The serve-time integrity gate compares sha256(verbatim_text) with
    # transcript_hash, so the fixture must carry the real hash of its own text.
    span_hash = hashlib.sha256(span_text.encode("utf-8")).hexdigest()
    data = {
        "corpus_version": "ctx-v1",
        "guru_id": guru_id,
        "video_id": video_id,
        "source_asset_id": video_id,
        "source_span_id": make_source_span_id(
            guru_id=guru_id,
            video_id=video_id,
            corpus_version="ctx-v1",
            word_start=word_start,
            word_end=word_end,
            transcript_hash=span_hash,
        ),
        "parent_unit_id": parent_unit_id,
        "turn_id": f"turn_{n}",
        "turn_index": n,
        "source_span_index": n,
        "start_ms": 1000 * n,
        "end_ms": 1000 * n + 900,
        "word_start": word_start,
        "word_end": word_end,
        "speaker_id": guru_id,
        "speaker_role": SpeakerRole.GURU,
        "speaker_verified": True,
        "voice_verification_method": "ecapa_voxceleb_span_slice_v2",
        "voice_model_revision": "synthetic-model-rev",
        "voice_score": 0.91,
        "voice_margin": 0.22,
        "voice_threshold_applied": {"cosine_floor": 0.75, "margin_threshold": 0.15},
        "voice_calibration_id": "synthetic-calibration-v1",
        "voice_window_check": "pass",
        "voice_verified_at": "2026-11-02T00:00:00Z",
        "speaker_verification_status": "verified",
        "source_transcript_text": span_text,
        "verbatim_text": span_text,
        "transcript_hash": span_hash,
        "source_text_hash": clip_text_hash(span_text),
        "boundary_status": BoundaryStatus.VERIFIED,
        "completeness_status": CompletenessStatus.COMPLETE,
        "rights_cleared": True,
        "domain_rights_status": "licensed",
        "caption_status": "auto_transcript",
        "provenance_kind": ProvenanceKind.SPEECH_TURN_SPAN,
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
        "answer_role": AnswerRole.DIRECT,
    }
    data.update(overrides)
    return SourceSpan(**data)


def make_cross_parent_edge(predecessor: SourceSpan, opener: SourceSpan):
    return ValidatedCrossParentEdge._issue(
        predecessor,
        opener,
        predecessor_parent_end_ms=predecessor.end_ms,
        opener_parent_start_ms=opener.start_ms,
        issue_token=_VALIDATED_EDGE_ISSUE_TOKEN,
    )


def make_test_context(spans: list[SourceSpan], **overrides) -> ParentContext:
    unique: list[SourceSpan] = []
    for s in spans:
        if s.source_span_id not in {u.source_span_id for u in unique}:
            unique.append(s)
    parent_kwargs = {
        "corpus_version": unique[0].corpus_version,
        "guru_id": unique[0].guru_id,
        "video_id": unique[0].video_id,
        "parent_unit_id": unique[0].parent_unit_id,
        "ordered_source_span_ids": tuple(s.source_span_id for s in unique),
        "start_ms": unique[0].start_ms,
        "end_ms": unique[-1].end_ms,
        "parent_text_hash": clip_text_hash(" ".join(s.verbatim_text for s in unique)),
        "speaker_ids": (unique[0].guru_id,),
        "speaker_continuity": True,
        "boundary_status": BoundaryStatus.VERIFIED,
        "completeness_status": CompletenessStatus.COMPLETE,
    }
    parent_kwargs.update(overrides)
    return ParentContext(
        parent=ParentUnit(**parent_kwargs),
        spans=tuple(unique),
        hit_span_ids=(unique[0].source_span_id,),
        score=0.95,
    )


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    reset_harness_metrics()
    # The owner flag is the only enable (a store alone never turns the harness
    # on), so the wiring tests arm it explicitly. Tests that need the off state
    # pin False themselves.
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_collection", "")
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", False)
    monkeypatch.setattr(settings, "first_person_context_selector_enabled", False)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", False)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_enrichment_window_enabled", False)
    monkeypatch.setattr(settings, "first_person_graph_expansion_enabled", False)
    # The serve-time integrity gate calls YouTube availability (FI-16). These
    # tests are about harness wiring, not video liveness, and fixture video ids
    # are synthetic, so keep the check out of the network.
    monkeypatch.setattr(
        "services.first_person_pipeline.is_youtube_video_available", lambda _vid: True
    )
    monkeypatch.setattr(
        "services.first_person_context_harness.source_is_authoritatively_licensed",
        lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
    )
    monkeypatch.setattr(
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
    )


# A calibrated profile is what makes a served context a DIRECT answer. Without
# it the harness still serves the same verbatim text, but reports "related".
DIRECT_PROFILE = {"threshold": 0.45, "score_kind": "cosine", "claims": "conformance"}


def test_serving_single_span_direct_success(monkeypatch):
    """Context harness directly serves single span with verified citations."""
    span1 = make_test_span(n=0, text=TEXT_ONE)
    ctx = make_test_context([span1])

    mock_store = Mock()
    mock_store.retrieve.return_value = [ctx]

    pipeline = FirstPersonPipeline(
        store=Mock(),
        serene_mind_engine=Mock(),
        context_store=mock_store,
        calibration_profile=DIRECT_PROFILE,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="What is the nature of suffering?",
        query_dense_vector=[0.1] * 1024,
        teacher_id="krishnaji",
        cache_bypass=True,
    )

    assert result.status == "success"
    assert result.is_direct_answer is True
    assert result.answer_text == TEXT_ONE
    assert result.abstain_reason == "none"
    assert len(result.citations) == 1

    cit = result.citations[0]
    assert cit["video_id"] == span1.video_id
    assert cit["start_ms"] == span1.start_ms
    assert cit["end_ms"] == span1.end_ms
    assert cit["title"] == "Discourse by Sri Krishnaji"
    assert cit["speaker"] == "Sri Krishnaji"
    assert cit["verbatim_text"] == TEXT_ONE
    assert cit["is_verbatim"] is True
    assert cit["confidence"] == 0.95

    assert result.audio_playback_clip is not None
    assert result.audio_playback_clip["video_id"] == span1.video_id
    assert result.audio_playback_clip["start_sec"] == span1.start_ms // 1000
    assert result.stage_timings["total_ms"] > 0
    assert "retrieval_ms" in result.stage_timings


def test_serving_parent_context_multiple_spans(monkeypatch):
    """Context harness reconstructs multiple spans deterministically in order."""
    span1 = make_test_span(n=0, text=TEXT_ONE)
    span2 = make_test_span(n=1, text=TEXT_TWO, start_ms=10000, end_ms=11000)
    ctx = make_test_context([span1, span2])

    mock_store = Mock()
    mock_store.retrieve.return_value = [ctx]

    pipeline = FirstPersonPipeline(
        store=Mock(),
        serene_mind_engine=Mock(),
        context_store=mock_store,
        calibration_profile=DIRECT_PROFILE,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="What is suffering?",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=True,
    )

    assert result.status == "success"
    assert result.is_direct_answer is True
    expected_text = f"{TEXT_ONE} {TEXT_TWO}"
    assert result.answer_text == expected_text
    # Context citations remain one-per-child so cache replay can revalidate every
    # contributing source span independently.
    assert len(result.citations) == 2
    assert [citation["source_span_id"] for citation in result.citations] == [
        span1.source_span_id,
        span2.source_span_id,
    ]
    assert [citation["verbatim_text"] for citation in result.citations] == [TEXT_ONE, TEXT_TWO]
    assert result.answer_text == " ".join(
        citation["verbatim_text"] for citation in result.citations
    )


def test_local_editorial_set_selects_multiple_gated_video_contexts(monkeypatch):
    """The opt-in path selects only independently served contexts, without LLM glue."""
    monkeypatch.setattr(settings, "is_production", False)
    monkeypatch.setattr(settings, "first_person_editorial_set_selection_enabled", True)
    monkeypatch.setattr(settings, "first_person_facet_split_enabled", False)
    monkeypatch.setattr(settings, "first_person_harness_parallel_enabled", False)

    krishnaji_text = (
        "Love is not possession or dependence; it is freedom from fear, expectation, "
        "and the need to complete oneself through another."
    )
    preethaji_text = (
        "Love is a movement of openness in which one meets another without fear, "
        "control, expectation, or demand."
    )
    krishnaji_span = make_test_span(
        n=0,
        text=krishnaji_text,
        guru_id="krishnaji",
        video_id="vARTudIEq30",
        parent_unit_id="parent_love_k",
    )
    preethaji_span = make_test_span(
        n=0,
        text=preethaji_text,
        guru_id="preethaji",
        video_id="_GEMrEWCiXw",
        parent_unit_id="parent_love_p",
    )
    contexts = [make_test_context([krishnaji_span]), make_test_context([preethaji_span])]
    context_store = Mock()
    context_store.retrieve.return_value = contexts
    redis = Mock()
    redis.get.return_value = None
    legacy_store = Mock()
    legacy_store.collection = "first_person_v9"

    pipeline = FirstPersonPipeline(
        store=legacy_store,
        redis_client=redis,
        serene_mind_engine=Mock(),
        context_store=context_store,
        calibration_profile=DIRECT_PROFILE,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="What is love according to Krishnaji and Preethaji?",
        query_dense_vector=[0.1] * 1024,
        max_clips=2,
    )

    assert result.status == "weak_match", result.editorial_set
    assert result.is_direct_answer is False
    assert len(result.citations) == 2
    assert {citation["video_id"] for citation in result.citations} == {
        "vARTudIEq30",
        "_GEMrEWCiXw",
    }
    assert result.answer_text == "\n\n".join(
        citation["verbatim_text"] for citation in result.citations
    )
    editorial = result.to_dict()["editorial_set"]
    assert editorial["status"] == "partial"
    assert editorial["candidate_contexts"] == 2
    assert editorial["selected_contexts"] == 2
    assert editorial["planner_version"] == "first_person_facets_v1"
    assert editorial["selector_version"] == "first_person_set_selector_v3"
    context_store.retrieve.assert_called_once()
    assert context_store.retrieve.call_args.kwargs["limit_parents"] == 4
    redis.get.assert_not_called()
    redis.set.assert_not_called()


def test_editorial_set_conflict_is_returned_as_weak_non_direct_evidence(monkeypatch):
    monkeypatch.setattr(settings, "is_production", False)
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    monkeypatch.setattr(settings, "first_person_editorial_set_selection_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", False)
    krishnaji_text = (
        "Love is freedom from fear, and this openness shows itself in attention, relationship, "
        "and the whole movement of living together."
    )
    preethaji_text = (
        "Love is not freedom from fear; it is a quiet field of presence that arises through "
        "attentive listening, patience, and connection with another."
    )
    contexts = [
        make_test_context(
            [
                make_test_span(
                    n=0,
                    text=krishnaji_text,
                    guru_id="krishnaji",
                    video_id="vARTudIEq30",
                    parent_unit_id="conflict-parent-k",
                )
            ]
        ),
        make_test_context(
            [
                make_test_span(
                    n=0,
                    text=preethaji_text,
                    guru_id="preethaji",
                    video_id="_GEMrEWCiXw",
                    parent_unit_id="conflict-parent-p",
                )
            ]
        ),
    ]
    context_store = Mock()
    context_store.retrieve.return_value = contexts
    redis = Mock()
    redis.get.return_value = None
    pipeline = FirstPersonPipeline(
        store=Mock(collection="first_person_v9"),
        redis_client=redis,
        serene_mind_engine=Mock(),
        context_store=context_store,
        calibration_profile=DIRECT_PROFILE,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="What is love according to Krishnaji and Preethaji?",
        query_dense_vector=[0.1] * 1024,
        max_clips=2,
        cache_bypass=True,
    )

    assert result.status == "weak_match"
    assert result.is_direct_answer is False
    assert result.editorial_set["status"] == "conflicted"
    citation_texts = {citation["verbatim_text"] for citation in result.citations}
    assert citation_texts == {krishnaji_text, preethaji_text}
    assert result.answer_text == "\n\n".join(
        citation["verbatim_text"] for citation in result.citations
    )
    redis.get.assert_not_called()
    redis.set.assert_not_called()


def test_editorial_selection_map_disambiguates_duplicate_span_ids():
    import time

    from services.first_person_facet_planner import get_default_planner
    from services.first_person_pipeline import FirstPersonPipelineResult

    pipeline = FirstPersonPipeline(
        store=Mock(),
        serene_mind_engine=Mock(),
        calibration_profile=DIRECT_PROFILE,
    )
    shared_span_id = "deliberate-duplicate-span-id"
    first_text = "Love is an unconditioned movement of attention."
    second_text = "Love is the quiet presence that recognizes another person."
    first_span = make_test_span(
        n=0,
        text=first_text,
        guru_id="krishnaji",
        video_id="vARTudIEq30",
        parent_unit_id="love-parent-k",
    )
    second_span = make_test_span(
        n=0,
        text=second_text,
        guru_id="preethaji",
        video_id="_GEMrEWCiXw",
        parent_unit_id="love-parent-p",
    )
    contexts = [make_test_context([first_span]), make_test_context([second_span])]

    def _served_result(span, text):
        citation = pipeline._build_context_citation(span)
        # Deliberately collide the raw ID; selection-map identity must still
        # retain the exact source video, teacher, and parent.
        citation["source_span_id"] = shared_span_id
        return FirstPersonPipelineResult(
            answer_text=text,
            citations=[citation],
            status="success",
            is_direct_answer=True,
            latency_ms=1.0,
            fp_served=True,
        )

    combined = pipeline._build_editorial_set_result(
        "What is love?",
        [
            (contexts[0], _served_result(first_span, first_text)),
            (contexts[1], _served_result(second_span, second_text)),
        ],
        facets=get_default_planner().plan("What is love?"),
        max_clips=2,
        start_time=time.monotonic(),
        retrieval_ms=0.0,
        answerability="yes",
    )

    assert {citation["video_id"] for citation in combined.citations} == {
        "vARTudIEq30",
        "_GEMrEWCiXw",
    }
    assert combined.answer_text == "\n\n".join(
        citation["verbatim_text"] for citation in combined.citations
    )


def test_editorial_set_rejects_noncontiguous_parent_span_identity():
    import time

    from services.first_person_facet_planner import get_default_planner
    from services.first_person_pipeline import FirstPersonPipelineResult

    pipeline = FirstPersonPipeline(
        store=Mock(),
        serene_mind_engine=Mock(),
        calibration_profile=DIRECT_PROFILE,
    )
    span_zero = make_test_span(
        n=0,
        text="Love becomes clear when attention is present and the mind is quiet.",
        video_id="vARTudIEq30",
        parent_unit_id="love-parent-contiguous",
    )
    span_two = make_test_span(
        n=2,
        text="In relationship, one may discover fear and the movement of dependence.",
        video_id="vARTudIEq30",
        parent_unit_id="love-parent-contiguous",
    )
    context = make_test_context([span_zero, span_two])
    citations = [pipeline._build_context_citation(span) for span in (span_zero, span_two)]
    result = FirstPersonPipelineResult(
        answer_text=" ".join(citation["verbatim_text"] for citation in citations),
        citations=citations,
        status="success",
        is_direct_answer=True,
        latency_ms=1.0,
        fp_served=True,
    )

    combined = pipeline._build_editorial_set_result(
        "What is love?",
        [(context, result)],
        facets=get_default_planner().plan("What is love?"),
        max_clips=1,
        start_time=time.monotonic(),
        retrieval_ms=0.0,
        answerability="yes",
    )

    assert combined.status == "abstained"
    assert combined.is_direct_answer is False
    assert combined.citations == []
    assert combined.editorial_set["candidate_contexts"] == 0


def test_editorial_set_abstains_on_caller_query_teacher_conflict(monkeypatch):
    monkeypatch.setattr(settings, "is_production", False)
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    monkeypatch.setattr(settings, "first_person_editorial_set_selection_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", False)
    context_store = Mock()
    redis = Mock()
    pipeline = FirstPersonPipeline(
        store=Mock(collection="first_person_v9"),
        redis_client=redis,
        serene_mind_engine=Mock(),
        context_store=context_store,
        calibration_profile=DIRECT_PROFILE,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="What is love according to Krishnaji?",
        query_dense_vector=[0.1] * 1024,
        teacher_id="preethaji",
        cache_bypass=True,
    )

    assert result.status == "abstained"
    assert result.is_direct_answer is False
    assert result.abstain_reason == "no_verified_clips"
    assert result.citations == []
    assert result.editorial_set["status"] == "insufficient"
    assert result.editorial_set["teacher_scope"] == "preethaji"
    context_store.retrieve.assert_not_called()
    redis.get.assert_not_called()
    redis.set.assert_not_called()


@pytest.mark.parametrize(
    ("case", "query", "candidate_text", "expected_reason"),
    [
        (
            "ordinary_anxiety",
            "What can I understand about anxiety?",
            "Anxiety may arise when the mind anticipates danger, and noticing fear without judgment "
            "brings attention back to the present moment with greater steadiness.",
            None,
        ),
        (
            "unsolicited_self_harm",
            "What is love?",
            "People who engage in self-harm often feel disconnected; compassionate support can help "
            "them express pain they carry alone and reconnect with others.",
            "unsolicited_self_harm_reference",
        ),
        (
            "event_bound",
            "What is love?",
            "During the covid pandemic, many people had to rethink how they cope with uncertainty; "
            "the event changed many conversations about human connection.",
            "event_marker",
        ),
        (
            "medical_claim",
            "What is love?",
            "Meditation has been scientifically proven to cure depression and anxiety, and this "
            "method has transformed every person who tried it.",
            "health_claim",
        ),
        (
            "outcome_promise",
            "What is love?",
            "If you follow this practice, you will definitely achieve lasting happiness for the rest "
            "of your life and never experience fear again.",
            "outcome_promise",
        ),
        (
            "dangling_question_tail",
            "What is suffering?",
            "Suffering asks us to observe the mind carefully as it moves through the day. "
            "But how can we?",
            "dangling_question_tail",
        ),
    ],
)
def test_phase3_policy_gates_actual_context_pipeline_before_selection(
    monkeypatch, case, query, candidate_text, expected_reason
):
    """The shared safety facade runs on real context candidates before a set can serve."""
    from services.first_person_evidence_policy import first_person_evidence_policy

    monkeypatch.setattr(settings, "is_production", False)
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", True)
    monkeypatch.setattr(settings, "first_person_editorial_set_selection_enabled", False)
    monkeypatch.setattr(settings, "first_person_facet_split_enabled", False)
    span = make_test_span(
        n=0,
        text=candidate_text,
        guru_id="krishnaji",
        video_id="vARTudIEq30",
        parent_unit_id=f"parent_{case}",
    )
    context_store = Mock()
    context_store.retrieve.return_value = [make_test_context([span])]
    legacy_store = Mock()
    legacy_store.collection = "first_person_v9"
    pipeline = FirstPersonPipeline(
        store=legacy_store,
        serene_mind_engine=Mock(),
        context_store=context_store,
        calibration_profile=DIRECT_PROFILE,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    observed = []
    original_contextual = first_person_evidence_policy.assess_contextual_safety
    original_standalone = first_person_evidence_policy.assess_context_standalone

    def _observe(query_text, candidate, *, retrieval_query=""):
        decision = original_contextual(query_text, candidate, retrieval_query=retrieval_query)
        observed.append(decision)
        return decision

    def _observe_standalone(texts, *args, **kwargs):
        decision = original_standalone(texts, *args, **kwargs)
        observed.append(decision)
        return decision

    monkeypatch.setattr(first_person_evidence_policy, "assess_contextual_safety", _observe)
    monkeypatch.setattr(
        first_person_evidence_policy, "assess_context_standalone", _observe_standalone
    )
    result = pipeline.execute(query=query, query_dense_vector=[0.1] * 1024, cache_bypass=True)

    assert observed, f"{case}: shared safety facade was not called"
    if expected_reason is None:
        assert any(decision.may_serve for decision in observed)
        assert result.status == "success"
        assert len(result.citations) == 1
    else:
        assert any(expected_reason in decision.reason_codes for decision in observed), case
        assert result.status == "abstained"
        assert result.citations == []
        legacy_store.search_hybrid.assert_not_called()


@pytest.mark.answerability_real
@pytest.mark.parametrize("verdict", ["NO", "MAYBE"])
def test_context_answerability_withheld_before_workers_or_scorer(monkeypatch, verdict):
    """A context NO/indeterminate verdict is final before harness scoring."""
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", True)
    monkeypatch.setattr(settings, "first_person_llm_rerank_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", False)
    monkeypatch.setattr(settings, "first_person_harness_parallel_enabled", False)

    span = make_test_span(n=0, text=TEXT_ONE)
    context_store = Mock()
    context_store.retrieve.return_value = [make_test_context([span])]
    legacy_store = Mock()
    legacy_store.search_hybrid.return_value = []
    llm = Mock()
    llm.generate.return_value = verdict
    scorer = Mock(side_effect=AssertionError("context answerability must short-circuit scorer"))
    monkeypatch.setattr("services.first_person_pipeline._relevance_select", scorer)

    pipeline = FirstPersonPipeline(
        store=legacy_store,
        serene_mind_engine=Mock(),
        context_store=context_store,
        llm_service=llm,
        calibration_profile=DIRECT_PROFILE,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="What is the capital of France?",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=True,
    )

    assert result.status == "abstained"
    assert result.answerability == ("no" if verdict == "NO" else "indeterminate")
    assert result.abstain_reason == "answerability_withheld"
    assert result.citations == []
    assert context_store.retrieve.call_count == 1
    legacy_store.search_hybrid.assert_not_called()
    scorer.assert_not_called()
    # The only provider call is the question-only answerability gate.
    assert llm.generate.call_count == (
        1 if verdict == "NO" else 2
    )  # unparseable gets one retry (L-03)
    assert llm.generate.call_args.kwargs["user_prompt"].startswith("What is the capital of France?")


def test_pipeline_fetches_validated_predecessor_before_harness_decision(monkeypatch):
    """The exact typed predecessor enters the harness before any decision."""
    selected = make_test_span(
        n=1,
        text="Imagine what will be the outcome of it, when attention remains clear.",
        parent_unit_id="current-parent",
        start_ms=10000,
        end_ms=11000,
        word_start=10,
        word_end=16,
    )
    predecessor = make_test_span(
        n=0,
        text=TEXT_ONE,
        parent_unit_id="previous-parent",
        start_ms=9000,
        end_ms=9900,
        word_start=0,
        word_end=6,
    )
    predecessor = predecessor.model_copy(update={"next_span_id": selected.source_span_id})
    selected = selected.model_copy(update={"previous_span_id": predecessor.source_span_id})
    ctx = make_test_context([selected])

    mock_context_store = Mock()
    mock_context_store.retrieve.return_value = [ctx]
    edge = make_cross_parent_edge(predecessor, selected)
    mock_context_store.fetch_preceding_span.return_value = edge
    events: list[str] = []
    mock_context_store.fetch_preceding_span.side_effect = lambda _span: (
        events.append("fetch") or edge
    )
    real_decide = FirstPersonContextHarness.decide

    def ordered_decide(self, *args, **kwargs):
        events.append("decide")
        return real_decide(self, *args, **kwargs)

    monkeypatch.setattr(FirstPersonContextHarness, "decide", ordered_decide)

    pipeline = FirstPersonPipeline(
        store=Mock(),
        serene_mind_engine=Mock(),
        context_store=mock_context_store,
        calibration_profile=DIRECT_PROFILE,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="What is suffering?",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=True,
    )

    assert result.answer_text == f"{TEXT_ONE} {selected.verbatim_text}"
    assert [citation["verbatim_text"] for citation in result.citations] == [
        TEXT_ONE,
        selected.verbatim_text,
    ]
    assert events == ["fetch", "decide"]
    mock_context_store.fetch_preceding_span.assert_called_once_with(selected)
    mock_context_store.fetch_succeeding_span.assert_not_called()


def _cross_parent_serving_context():
    opener = make_test_span(
        n=1,
        text="Imagine what will be the outcome of it, when attention remains clear.",
        parent_unit_id="current-parent",
        start_ms=10000,
        end_ms=11000,
        word_start=10,
        word_end=16,
    )
    predecessor = make_test_span(
        n=0,
        text="The river of awareness moves without resistance.",
        parent_unit_id="previous-parent",
        start_ms=9000,
        end_ms=9900,
        word_start=0,
        word_end=6,
    )
    predecessor = predecessor.model_copy(update={"next_span_id": opener.source_span_id})
    opener = opener.model_copy(update={"previous_span_id": predecessor.source_span_id})
    return predecessor, opener, make_test_context([opener])


def test_two_parent_context_result_is_never_written_to_exact_cache():
    predecessor, opener, ctx = _cross_parent_serving_context()
    mock_context_store = Mock()
    mock_context_store.retrieve.return_value = [ctx]
    mock_context_store.fetch_preceding_span.return_value = make_cross_parent_edge(
        predecessor, opener
    )
    mock_redis = Mock()
    mock_redis.get.return_value = None

    pipeline = FirstPersonPipeline(
        store=Mock(),
        redis_client=mock_redis,
        serene_mind_engine=Mock(),
        context_store=mock_context_store,
        calibration_profile=DIRECT_PROFILE,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="What is awareness?",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=False,
    )

    assert result.answer_text == f"{predecessor.verbatim_text} {opener.verbatim_text}"
    mock_redis.set.assert_not_called()


def test_context_cache_replay_rechecks_the_reconstructed_joined_body(monkeypatch):
    first = make_test_span(
        n=0,
        text=(
            "Suffering is a call to awaken, inviting you to meet resistance with "
            "awareness and compassion."
        ),
        video_id="UlOt31lBhLY",
    )
    second = make_test_span(
        n=1,
        text="This truth can set us free.",
        video_id="UlOt31lBhLY",
        start_ms=10000,
        end_ms=11000,
    )
    ctx = make_test_context([first, second])
    mock_context_store = Mock()
    mock_context_store.retrieve.return_value = [ctx]
    mock_context_store.fresh_spans_for_citations.return_value = [first, second]
    legacy_store = Mock()
    legacy_store.search_hybrid.return_value = []
    cache_store: dict[str, str] = {}
    mock_redis = Mock()
    mock_redis.get.side_effect = lambda key: cache_store.get(key)
    mock_redis.set.side_effect = lambda key, value, ex=None: cache_store.__setitem__(key, value)

    pipeline = FirstPersonPipeline(
        store=legacy_store,
        redis_client=mock_redis,
        serene_mind_engine=Mock(),
        context_store=mock_context_store,
        calibration_profile=DIRECT_PROFILE,
    )
    pipeline._serene_mind.assess_distress.return_value = None
    first_result = pipeline.execute(
        query="What is suffering?",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=False,
    )
    assert first_result.cached is False

    joined = f"{first.verbatim_text} {second.verbatim_text}"

    class Safety:
        reason_codes = ("violent_relationship_context",)

        def __init__(self, may_serve):
            self.may_serve = may_serve

    safety_bodies: list[str] = []

    def body_safety(_query, body, retrieval_query=""):
        safety_bodies.append(body)
        return Safety(body != joined)

    monkeypatch.setattr(
        "services.first_person_pipeline.first_person_evidence_policy.assess_contextual_safety",
        body_safety,
    )
    cache_key = next(iter(cache_store))
    tampered = json.loads(cache_store[cache_key])
    tampered["answer_text"] = "Injected serialized answer text that must never be replayed."
    cache_store[cache_key] = json.dumps(tampered)
    safety_bodies.clear()
    replay = pipeline.execute(
        query="What is suffering?",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=False,
    )

    assert replay.cached is False
    assert mock_context_store.retrieve.call_count == 2
    # Replay safety must inspect the freshly reconstructed joined body, not the
    # tampered serialized answer_text. Rejecting that body proves the replay
    # fails closed before any stale cache payload can be returned.
    assert safety_bodies[-1] == joined
    assert "Injected serialized answer text" not in safety_bodies


def test_pipeline_rejects_context_when_any_selected_child_fails_a_gate():
    """A parent context is all-or-nothing; one bad child cannot be served."""
    good = make_test_span(n=0, text=TEXT_ONE)
    bad = make_test_span(n=1, text=TEXT_TWO, rights_cleared=False, start_ms=10000, end_ms=11000)
    ctx = make_test_context([good, bad])

    mock_context_store = Mock()
    mock_context_store.retrieve.return_value = [ctx]
    mock_legacy_store = Mock()
    mock_legacy_store.search_hybrid.return_value = []
    mock_legacy_store.collection = "first_person_v9"
    pipeline = FirstPersonPipeline(
        store=mock_legacy_store,
        serene_mind_engine=Mock(),
        context_store=mock_context_store,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="What is suffering?",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=True,
    )

    assert result.citations == []
    assert result.answer_text == "No verified first-person discourse found for this question."
    mock_legacy_store.search_hybrid.assert_called_once()


def test_provider_relevance_failure_fails_closed(monkeypatch):
    """A provider refusal/error cannot fall through to local uncalibrated scoring."""
    monkeypatch.setattr(settings, "first_person_relevance_min_score", 3)
    monkeypatch.setattr(settings, "first_person_relevance_model", "")

    failing_provider = Mock()
    failing_provider.generate.side_effect = RuntimeError("budget denied")
    scores: list[int] = []
    result = _relevance_select_scored(
        "What is suffering?",
        [{"verbatim_text": TEXT_ONE}],
        failing_provider,
        scores_out=scores,
    )

    assert result == -1
    assert scores == []


def test_serving_without_calibration_profile_is_related_not_direct(monkeypatch):
    """Served harness text without a loaded profile must not claim to be direct."""
    span1 = make_test_span(n=0, text=TEXT_ONE)
    ctx = make_test_context([span1])

    mock_store = Mock()
    mock_store.retrieve.return_value = [ctx]

    pipeline = FirstPersonPipeline(
        store=Mock(),
        serene_mind_engine=Mock(),
        context_store=mock_store,
        calibration_profile=None,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="What is the nature of suffering?",
        query_dense_vector=[0.1] * 1024,
        teacher_id="krishnaji",
        cache_bypass=True,
    )

    # No calibration profile -> not direct -> the honest "related" label. The
    # STATUS must say so too: the bridge serves a "success" answer only when
    # is_direct_answer is true, so a "success" label here made every harness
    # answer collapse into a static abstention.
    assert result.status == "weak_match"
    assert result.answer_text == TEXT_ONE
    assert result.is_direct_answer is False


def test_serving_never_accepts_llm_hallucinated_text(monkeypatch):
    """Even if an LLM generates text, harness answer_text is strictly stored spans."""
    span1 = make_test_span(n=0, text=TEXT_ONE)
    ctx = make_test_context([span1])

    mock_store = Mock()
    mock_store.retrieve.return_value = [ctx]

    mock_llm = Mock()
    mock_llm.generate.return_value = "I am an AI that authored this answer."

    pipeline = FirstPersonPipeline(
        store=Mock(),
        serene_mind_engine=Mock(),
        llm_service=mock_llm,
        context_store=mock_store,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="Tell me about suffering",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=True,
    )

    assert result.status == "weak_match"
    assert result.answer_text == TEXT_ONE
    assert "I am an AI" not in result.answer_text


def test_hybrid_fp_context_keeps_the_gated_verbatim_body(monkeypatch):
    monkeypatch.setattr(settings, "first_person_mode", "hybrid")
    span1 = make_test_span(n=0, text=TEXT_ONE)
    ctx = make_test_context([span1])
    mock_store = Mock()
    mock_store.retrieve.return_value = [ctx]
    mock_weaver = Mock()
    mock_weaver.weave.return_value = Mock(
        passed_gate=True,
        text="Generated connective prose that must not replace the quote.",
    )

    pipeline = FirstPersonPipeline(
        store=Mock(),
        serene_mind_engine=Mock(),
        context_store=mock_store,
        weaver=mock_weaver,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="Tell me about suffering",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=True,
    )

    assert result.answer_text == TEXT_ONE
    mock_weaver.weave.assert_not_called()


def test_fallback_when_context_harness_abstains(monkeypatch):
    """When context harness abstains (e.g. rights not cleared), falls back to legacy pipeline."""
    span1 = make_test_span(n=0, text=TEXT_ONE, rights_cleared=False)
    ctx = make_test_context([span1], completeness_status=CompletenessStatus.COMPLETE)

    mock_ctx_store = Mock()
    mock_ctx_store.retrieve.return_value = [ctx]

    # Legacy store returns a clip
    legacy_clip = {
        "point_id": "legacy_clip_1",
        "video_id": "vid_legacy",
        "start_ms": 5000,
        "end_ms": 10000,
        "speaker": "Sri Krishnaji",
        "teacher_id": "krishnaji",
        "verbatim_text": "Legacy clip text.",
        "transcript_hash": "b" * 64,
        "rights_cleared": True,
        "domain_rights_status": "licensed",
        "first_person_eligible": True,
        "passage_dense": [0.1] * 1024,
    }
    mock_legacy_store = Mock()
    mock_legacy_store.search_hybrid.return_value = [legacy_clip]
    mock_legacy_store.collection = "first_person_v9"

    pipeline = FirstPersonPipeline(
        store=mock_legacy_store,
        serene_mind_engine=Mock(),
        context_store=mock_ctx_store,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    # Patch legacy passes to verify fallback was taken
    with (
        patch("services.first_person_pipeline._passes_integrity_gate", return_value=True),
        patch("services.first_person_pipeline._passes_content_quality_gate", return_value=True),
    ):
        pipeline.execute(
            query="Tell me something",
            query_dense_vector=[0.1] * 1024,
            cache_bypass=True,
        )

    # Context store was retrieved, harness abstained, legacy search_hybrid was called
    mock_ctx_store.retrieve.assert_called_once()
    mock_legacy_store.search_hybrid.assert_called_once()


def test_fallback_when_context_store_returns_empty():
    """When context store returns empty list, falls back gracefully to legacy pipeline."""
    mock_ctx_store = Mock()
    mock_ctx_store.retrieve.return_value = []

    mock_legacy_store = Mock()
    mock_legacy_store.search_hybrid.return_value = []
    mock_legacy_store.collection = "first_person_v9"

    pipeline = FirstPersonPipeline(
        store=mock_legacy_store,
        serene_mind_engine=Mock(),
        context_store=mock_ctx_store,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    pipeline.execute(
        query="Tell me something",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=True,
    )

    mock_ctx_store.retrieve.assert_called_once()
    mock_legacy_store.search_hybrid.assert_called_once()


def test_fallback_when_context_store_raises_exception():
    """When context store raises an unexpected error, catches and falls back to legacy."""
    mock_ctx_store = Mock()
    mock_ctx_store.retrieve.side_effect = RuntimeError("Qdrant transient error")

    mock_legacy_store = Mock()
    mock_legacy_store.search_hybrid.return_value = []
    mock_legacy_store.collection = "first_person_v9"

    pipeline = FirstPersonPipeline(
        store=mock_legacy_store,
        serene_mind_engine=Mock(),
        context_store=mock_ctx_store,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    pipeline.execute(
        query="Tell me something",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=True,
    )

    mock_ctx_store.retrieve.assert_called_once()
    mock_legacy_store.search_hybrid.assert_called_once()


def test_flag_off_never_invokes_context_store(monkeypatch):
    """The owner flag is the only enable: even an injected context store stays
    dormant while first_person_context_harness_enabled is False."""
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", False)
    monkeypatch.setattr(settings, "first_person_context_collection", "")

    mock_legacy_store = Mock()
    mock_legacy_store.search_hybrid.return_value = []
    mock_legacy_store.collection = "first_person_v9"

    pipeline = FirstPersonPipeline(
        store=mock_legacy_store,
        serene_mind_engine=Mock(),
    )
    pipeline._serene_mind.assess_distress.return_value = None

    pipeline.execute(
        query="Tell me something",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=True,
    )

    assert pipeline._context_store is None
    mock_legacy_store.search_hybrid.assert_called_once()


def test_exact_caching_for_context_harness_result(monkeypatch):
    """Context harness answers are written to exact cache and replayed on hit."""
    span1 = make_test_span(n=0, text=TEXT_ONE, video_id="UlOt31lBhLY")
    ctx = make_test_context([span1])

    mock_store = Mock()
    mock_store.retrieve.return_value = [ctx]
    # Exact-cache replay must hydrate current validated spans, not trust the
    # citation/display fields serialized into Redis.
    mock_store.fresh_spans_for_citations.return_value = [span1]

    # In-memory mock redis client
    cache_store = {}
    mock_redis = Mock()

    def _get(key):
        return cache_store.get(key)

    def _set(key, val, ex=None):
        cache_store[key] = val

    mock_redis.get.side_effect = _get
    mock_redis.set.side_effect = _set

    mock_legacy_store = Mock()
    mock_legacy_store.points_servable.return_value = True

    pipeline = FirstPersonPipeline(
        store=mock_legacy_store,
        redis_client=mock_redis,
        serene_mind_engine=Mock(),
        context_store=mock_store,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    # First call: cache miss, executes harness
    res1 = pipeline.execute(
        query="What is suffering?",
        query_dense_vector=[0.1] * 1024,
        teacher_id="krishnaji",
        cache_bypass=False,
    )
    assert res1.status == "weak_match"
    assert res1.cached is False
    assert mock_store.retrieve.call_count == 1

    # Second call: cache hit!
    res2 = pipeline.execute(
        query="What is suffering?",
        query_dense_vector=[0.1] * 1024,
        teacher_id="krishnaji",
        cache_bypass=False,
    )
    assert res2.status == "weak_match"
    assert res2.cached is True
    assert res2.answer_text == res1.answer_text
    assert mock_store.retrieve.call_count == 1  # No second retrieval

    # Positive servability decisions are not reused across cache hits.
    res3 = pipeline.execute(
        query="What is suffering?",
        query_dense_vector=[0.1] * 1024,
        teacher_id="krishnaji",
        cache_bypass=False,
    )
    assert res3.cached is True
    assert mock_store.fresh_spans_for_citations.call_count == 2
    assert mock_store.points_servable.call_count == 0
    assert mock_legacy_store.points_servable.call_count == 0

    # Tamper cached body and representative derived citation fields. A cache
    # hit remains safe because body/citations are rebuilt from current
    # validated SourceSpan data, not trusted from Redis.
    cache_key = next(iter(cache_store))
    tampered = json.loads(cache_store[cache_key])
    tampered["answer_text"] = "Injected prose not present in the citations."
    tampered["citations"][0].update(
        {
            "speaker": "Injected speaker",
            "title": "Injected title",
            "url": "https://evil.example/not-the-source",
            "teacher_id": "injected-teacher",
            "start_ms": 999999,
            "playback_url": "https://evil.example/play?t=999999",
        }
    )
    cache_store[cache_key] = json.dumps(tampered)
    res4 = pipeline.execute(
        query="What is suffering?",
        query_dense_vector=[0.1] * 1024,
        teacher_id="krishnaji",
        cache_bypass=False,
    )
    assert res4.cached is True
    assert res4.answer_text == TEXT_ONE
    assert res4.citations[0]["speaker"] == "Sri Krishnaji"
    assert res4.citations[0]["title"] == "Discourse by Sri Krishnaji"
    assert res4.citations[0]["url"] == span1.source_url
    assert res4.citations[0]["teacher_id"] == span1.guru_id
    assert res4.citations[0]["start_ms"] == span1.start_ms
    assert res4.citations[0]["playback_url"].startswith(
        f"https://www.youtube.com/watch?v={span1.video_id}"
    )
    assert mock_store.retrieve.call_count == 1

    # A current-payload change is not independently verifiable against cached
    # evidence, so context cache replay fails closed instead of returning stale
    # text or attribution.
    mock_store.fresh_spans_for_citations.return_value = None
    res5 = pipeline.execute(
        query="What is suffering?",
        query_dense_vector=[0.1] * 1024,
        teacher_id="krishnaji",
        cache_bypass=False,
    )
    assert res5.cached is False
    assert mock_store.retrieve.call_count == 2


def test_exact_cache_preserves_legacy_quote_plus_attribution_body():
    """Legacy exact-cache entries are not rewritten into raw quote joins."""
    cache_store = {}
    mock_redis = Mock()
    mock_redis.get.side_effect = lambda key: cache_store.get(key)
    legacy_store = Mock()
    legacy_store.points_servable.return_value = True
    pipeline = FirstPersonPipeline(
        store=legacy_store,
        redis_client=mock_redis,
        serene_mind_engine=Mock(),
    )
    quote = TEXT_ONE
    answer = f'"{quote}"\n— Sri Krishnaji (legacy-video, 12s)'
    query = "What is suffering?"
    data = {
        "answer_text": answer,
        "citations": [
            {
                "point_id": "legacy-point",
                "video_id": "legacy-video",
                "verbatim_text": quote,
                "transcript_hash": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
                "speaker": "Sri Krishnaji",
                "is_verbatim": True,
                "first_person_eligible": True,
                "rights_cleared": True,
                "domain_rights_status": "licensed",
                "source_url": "https://www.youtube.com/watch?v=legacy-video&t=12s",
            }
        ],
        "status": "weak_match",
        "is_direct_answer": False,
        "abstain_reason": "none",
    }
    cache_store[pipeline._get_exact_cache_key(query)] = json.dumps(data)

    hit = pipeline.check_exact_cache(query, retrieval_query=query)

    assert hit is not None
    assert hit["answer_text"] == answer
    assert legacy_store.points_servable.call_count == 1


def test_context_citation_playback_end_is_capped_by_media_duration():
    """A-19: parity with the legacy citation path. When the span knows the
    recording length, the +pad must not point past the end of the video."""
    from services.first_person_pipeline import CITATION_PLAYBACK_PAD_S

    pipeline = FirstPersonPipeline(store=Mock(), serene_mind_engine=Mock())
    span = make_test_span(n=0, start_ms=50_000, end_ms=59_900, duration_ms=60_000)

    citation = pipeline._build_context_citation(span)

    assert citation["playback_end_seconds"] == 60.0
    assert citation["playback_end_seconds"] <= span.duration_ms / 1000.0
    # The window still covers the quoted words.
    assert citation["playback_end_seconds"] >= citation["end_ms"] / 1000.0
    assert citation["playback_start_seconds"] == round(50.0 - CITATION_PLAYBACK_PAD_S, 2)


def test_context_citation_without_known_duration_keeps_the_documented_pad():
    """The fp-context payloads carry no media duration, so the residual
    (at most CITATION_PLAYBACK_PAD_S past the clip end) is the honest state —
    it must not be invented from ``end_ms``."""
    from services.first_person_pipeline import CITATION_PLAYBACK_PAD_S

    pipeline = FirstPersonPipeline(store=Mock(), serene_mind_engine=Mock())
    span = make_test_span(n=0, start_ms=50_000, end_ms=59_900)

    assert span.duration_ms is None
    citation = pipeline._build_context_citation(span)

    assert citation["playback_end_seconds"] == round(59.9 + CITATION_PLAYBACK_PAD_S, 2)
    assert citation["playback_end_seconds"] - citation["end_ms"] / 1000.0 == pytest.approx(
        CITATION_PLAYBACK_PAD_S
    )


def test_hybrid_fp_context_result_is_not_written_to_exact_cache(monkeypatch):
    """Optional hybrid framing stays live when its body is not reconstructible."""
    monkeypatch.setattr(settings, "first_person_mode", "hybrid")
    span1 = make_test_span(n=0, text=TEXT_ONE)
    cache_store = {}
    mock_redis = Mock()
    mock_redis.set.side_effect = lambda key, value, ex=None: cache_store.__setitem__(key, value)
    pipeline = FirstPersonPipeline(
        store=Mock(),
        redis_client=mock_redis,
        serene_mind_engine=Mock(),
        context_store=Mock(),
    )
    citation = pipeline._build_context_citation(span1)
    assert citation["domain_rights_status"] == "licensed"
    data = {
        "answer_text": f"Opening prose. {TEXT_ONE}",
        "citations": [citation],
        "status": "weak_match",
        "is_direct_answer": False,
    }

    pipeline.set_exact_cache("What is suffering?", data)

    assert cache_store == {}


def test_hybrid_legacy_exact_cache_read_and_write_are_disabled(monkeypatch):
    """Hybrid mode never replays or stores legacy quote-plus-attribution bodies."""
    monkeypatch.setattr(settings, "first_person_mode", "hybrid")
    cache_store = {}
    mock_redis = Mock()
    mock_redis.get.side_effect = lambda key: cache_store.get(key)
    mock_redis.set.side_effect = lambda key, value, ex=None: cache_store.__setitem__(key, value)
    legacy_store = Mock()
    pipeline = FirstPersonPipeline(
        store=legacy_store,
        redis_client=mock_redis,
        serene_mind_engine=Mock(),
    )
    data = {
        "answer_text": f'"{TEXT_ONE}"\n— Sri Krishnaji (legacy-video, 12s)',
        "citations": [
            {
                "point_id": "legacy-point",
                "video_id": "legacy-video",
                "verbatim_text": TEXT_ONE,
                "transcript_hash": hashlib.sha256(TEXT_ONE.encode("utf-8")).hexdigest(),
                "speaker": "Sri Krishnaji",
                "is_verbatim": True,
            }
        ],
        "status": "weak_match",
        "is_direct_answer": False,
    }

    pipeline.set_exact_cache("What is suffering?", data)
    assert cache_store == {}

    cache_store[pipeline._get_exact_cache_key("What is suffering?")] = json.dumps(data)
    assert (
        pipeline.check_exact_cache("What is suffering?", retrieval_query="What is suffering?")
        is None
    )
    mock_redis.get.assert_not_called()
    legacy_store.points_servable.assert_not_called()


def test_hybrid_compound_result_is_not_written_to_exact_cache(monkeypatch):
    """Compound legacy results use the same hybrid no-cache boundary."""
    monkeypatch.setattr(settings, "first_person_mode", "hybrid")
    cache_store = {}
    mock_redis = Mock()
    mock_redis.set.side_effect = lambda key, value, ex=None: cache_store.__setitem__(key, value)
    pipeline = FirstPersonPipeline(
        store=Mock(),
        redis_client=mock_redis,
        serene_mind_engine=Mock(),
    )
    pipeline.set_exact_cache(
        "What is suffering and meditation?",
        {
            "answer_text": "compound quote layout",
            "citations": [
                {
                    "point_id": "compound-point",
                    "video_id": "compound-video",
                    "verbatim_text": TEXT_ONE,
                    "transcript_hash": hashlib.sha256(TEXT_ONE.encode("utf-8")).hexdigest(),
                    "speaker": "Sri Krishnaji",
                    "is_verbatim": True,
                    "provenance_kind": "compound_facet_clip",
                }
            ],
            "status": "success",
            "is_direct_answer": True,
        },
    )

    assert cache_store == {}


@pytest.mark.parametrize("malformation", ["mixed_parent", "reordered"])
def test_context_cache_malformations_fail_closed_via_fresh_validation(malformation):
    """Cache replay delegates the whole citation set to fresh parent validation."""
    first = make_test_span(n=0, text=TEXT_ONE)
    second = make_test_span(n=1, text=TEXT_TWO, start_ms=10000, end_ms=11000)
    context_store = Mock()
    context_store.fresh_spans_for_citations.return_value = None
    legacy_store = Mock()
    pipeline = FirstPersonPipeline(
        store=legacy_store,
        redis_client=Mock(),
        serene_mind_engine=Mock(),
        context_store=context_store,
    )
    citations = [pipeline._build_context_citation(first), pipeline._build_context_citation(second)]
    if malformation == "mixed_parent":
        citations[1]["parent_unit_id"] = "different-parent"
    else:
        citations.reverse()
    cache_store = {
        pipeline._get_exact_cache_key("What is suffering?"): json.dumps(
            {
                "answer_text": " ".join(c["verbatim_text"] for c in citations),
                "citations": citations,
                "status": "weak_match",
                "is_direct_answer": False,
            }
        )
    }
    pipeline._redis.get.side_effect = lambda key: cache_store.get(key)

    assert (
        pipeline.check_exact_cache("What is suffering?", retrieval_query="What is suffering?")
        is None
    )
    context_store.fresh_spans_for_citations.assert_called_once()
    legacy_store.points_servable.assert_not_called()


def test_policy_fingerprint_covers_the_context_collection(monkeypatch):
    """Repointing the harness at a different fp-context corpus must re-key the
    exact cache.

    The collection decides which spans the harness can serve, so it is
    answer-shaping. Without it in the serving-policy digest, an answer
    computed against collection A would be replayed from the 24 h exact cache
    after the collection was repointed at B.
    """
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_collection", "fp_context_alpha")
    pipeline = FirstPersonPipeline(store=Mock(), redis_client=Mock(), serene_mind_engine=Mock())
    first = pipeline._serving_policy_fingerprint()

    monkeypatch.setattr(settings, "first_person_context_collection", "fp_context_beta")
    second = pipeline._serving_policy_fingerprint()
    assert first != second

    monkeypatch.setattr(settings, "first_person_context_collection", "fp_context_alpha")
    assert pipeline._serving_policy_fingerprint() == first


def test_policy_fingerprint_pins_evidence_policy_and_candidate_thresholds(monkeypatch):
    from domain.first_person_safety import SAFETY_POLICY_VERSION
    from services.first_person_evidence_policy import POLICY_VERSION

    monkeypatch.setattr(settings, "first_person_require_speaker_verified", False)
    pipeline = FirstPersonPipeline(store=Mock(), redis_client=Mock(), serene_mind_engine=Mock())
    base_components = pipeline._serving_policy_components()
    base = pipeline._serving_policy_fingerprint()
    assert base_components["first_person_evidence_policy"] == POLICY_VERSION
    assert SAFETY_POLICY_VERSION in POLICY_VERSION

    monkeypatch.setattr(settings, "first_person_require_speaker_verified", True)
    assert pipeline._serving_policy_components()["require_speaker_verified"] == "True"
    assert pipeline._serving_policy_fingerprint() != base

    monkeypatch.setattr(settings, "first_person_require_speaker_verified", False)
    monkeypatch.setattr(settings, "first_person_min_answer_words", 24)
    assert pipeline._serving_policy_components()["standalone_min_words"] == "24"
    assert pipeline._serving_policy_fingerprint() != base


def test_selector_integration(monkeypatch):
    """Phase D8 selector is consulted when enabled and its span order is honored."""
    monkeypatch.setattr(settings, "first_person_context_selector_enabled", True)

    span1 = make_test_span(n=0, text=TEXT_ONE)
    span2 = make_test_span(n=1, text=TEXT_TWO, start_ms=10000, end_ms=11000)
    ctx = make_test_context([span1, span2])

    mock_store = Mock()
    mock_store.retrieve.return_value = [ctx]

    # Mock selector returning only span2's id
    mock_llm = Mock()
    mock_llm.generate.return_value = f'{{"span_ids": ["{span2.source_span_id}"]}}'

    pipeline = FirstPersonPipeline(
        store=Mock(),
        serene_mind_engine=Mock(),
        llm_service=mock_llm,
        context_store=mock_store,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="Tell me about punishment",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=True,
    )

    assert result.status == "weak_match"
    assert result.answer_text == TEXT_TWO
    assert len(result.citations) == 1
    assert result.citations[0]["video_id"] == span2.video_id


def test_context_cache_replay_rejects_assembled_content_quality_failure(monkeypatch):
    first = make_test_span(n=0, text=TEXT_ONE)
    second = make_test_span(n=1, text=TEXT_TWO, start_ms=10000, end_ms=11000)
    context_store = Mock()
    context_store.fresh_spans_for_citations.return_value = [first, second]
    redis = Mock()
    pipeline = FirstPersonPipeline(
        store=Mock(),
        redis_client=redis,
        serene_mind_engine=Mock(),
        context_store=context_store,
    )
    citations = [pipeline._build_context_citation(first), pipeline._build_context_citation(second)]
    cached = {
        "answer_text": f"{TEXT_ONE} {TEXT_TWO}",
        "citations": citations,
        "status": "weak_match",
        "is_direct_answer": False,
    }
    redis.get.return_value = json.dumps(cached)
    monkeypatch.setattr(
        "services.first_person_pipeline._passes_content_quality_gate",
        lambda clip, gate_enabled=None: clip.get("verbatim_text") != cached["answer_text"],
    )

    assert (
        pipeline.check_exact_cache("What is suffering?", retrieval_query="What is suffering?")
        is None
    )


def test_context_cache_replay_rejects_assembled_boundary_failure(monkeypatch):
    first = make_test_span(n=0, text=TEXT_ONE)
    second = make_test_span(n=1, text=TEXT_TWO, start_ms=10000, end_ms=11000)
    context_store = Mock()
    context_store.fresh_spans_for_citations.return_value = [first, second]
    redis = Mock()
    pipeline = FirstPersonPipeline(
        store=Mock(),
        redis_client=redis,
        serene_mind_engine=Mock(),
        context_store=context_store,
    )
    citations = [pipeline._build_context_citation(first), pipeline._build_context_citation(second)]
    cached = {
        "answer_text": f"{TEXT_ONE} {TEXT_TWO}",
        "citations": citations,
        "status": "weak_match",
        "is_direct_answer": False,
    }
    redis.get.return_value = json.dumps(cached)
    pipeline._boundary_guard_enabled = True
    monkeypatch.setattr(
        "services.first_person_pipeline.boundary_defects",
        lambda _tokens: ["head_fragment"],
    )

    assert (
        pipeline.check_exact_cache("What is suffering?", retrieval_query="What is suffering?")
        is None
    )


def test_live_qdrant_fp_context_serving(monkeypatch):
    """End-to-end integration test against live Qdrant collection fp_context_v1_local."""
    client = QdrantClient("http://qdrant:6333")
    try:
        client.get_collection("fp_context_v1_local")
    except Exception as exc:
        pytest.skip(f"fp_context_v1_local not accessible: {exc}")

    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_collection", "fp_context_v1_local")
    monkeypatch.setattr(settings, "first_person_context_max_spans", 3)

    pipeline = FirstPersonPipeline(
        serene_mind_engine=Mock(),
    )
    pipeline._serene_mind.assess_distress.return_value = None

    # Retrieve vector for a known point in fp_context_v1_local to query
    pts = client.retrieve(
        "fp_context_v1_local",
        ids=["00393f98-c291-520b-9d90-5339ae058b62"],
        with_vectors=True,
    )
    if not pts or not pts[0].vector:
        pytest.skip("Could not fetch test vector from fp_context_v1_local")

    test_dense_vector = pts[0].vector.get("passage_dense")
    if not test_dense_vector:
        pytest.skip("Passage dense vector missing")

    result = pipeline.execute(
        query="How does feeling connected affect intelligence?",
        query_dense_vector=test_dense_vector,
        teacher_id="krishnaji",
        cache_bypass=True,
    )

    assert result.status == "success"
    # Directness is a calibrated-profile decision, not a harness decision: with
    # no loaded profile this answer is served as "related", so it is asserted
    # only where a profile is injected (see test_serving_single_span_direct_success).
    assert result.answer_text
    assert len(result.citations) >= 1
    assert "connected" in result.answer_text.lower()
    for cit in result.citations:
        assert cit["video_id"]
        assert cit["start_ms"] >= 0
        assert cit["end_ms"] > cit["start_ms"]
        assert cit["title"]
        assert cit["speaker"] in ("Sri Krishnaji", "Sri Preethaji")


def _run_with_scorer(monkeypatch, fake_select):
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    monkeypatch.setattr("services.first_person_pipeline._relevance_select", fake_select)
    mock_store = Mock()
    mock_store.retrieve.return_value = [make_test_context([make_test_span(n=0, text=TEXT_ONE)])]
    pipeline = FirstPersonPipeline(
        store=Mock(), serene_mind_engine=Mock(), context_store=mock_store
    )
    pipeline._serene_mind.assess_distress.return_value = None
    pipeline._store.search_hybrid.return_value = []
    return pipeline.execute(
        query="What is the nature of suffering?",
        query_dense_vector=[0.1] * 1024,
        teacher_id="krishnaji",
        cache_bypass=True,
    )


def test_harness_answer_scored_below_min_is_not_served(monkeypatch):
    def fake(query, clips, llm, loop=None, token_sink=None, scores_out=None, **kwargs):
        assert clips[0]["verbatim_text"] == TEXT_ONE
        scores_out[:] = [2]
        return None

    result = _run_with_scorer(monkeypatch, fake)
    assert result.answer_text != TEXT_ONE


def test_harness_answer_scored_at_min_is_served(monkeypatch):
    def fake(query, clips, llm, loop=None, token_sink=None, scores_out=None, judge_meta_out=None, **kwargs):
        scores_out[:] = [3]
        return 0

    result = _run_with_scorer(monkeypatch, fake)
    assert result.answer_text == TEXT_ONE
    assert result.stage_timings["relevance_score"] == 3.0


def test_harness_scorer_error_abstains(monkeypatch):
    from services.first_person_pipeline import _RELEVANCE_INDETERMINATE

    result = _run_with_scorer(monkeypatch, lambda *a, **k: _RELEVANCE_INDETERMINATE)
    assert result.status == "abstained"
    assert result.abstain_reason == "relevance_indeterminate"


def test_injected_context_store_is_dormant_when_the_owner_flag_is_off(monkeypatch):
    """P1-4 regression: store presence is configuration, not permission.

    Before this guard, `FirstPersonPipeline(context_store=...)` ran fp-context
    serving even though FIRST_PERSON_CONTEXT_HARNESS_ENABLED was false — the
    public-release NO-GO posture says the harness must not serve unless the
    owner flag says so.
    """
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", False)
    monkeypatch.setattr(settings, "first_person_context_collection", "")

    mock_context_store = Mock()
    mock_context_store.retrieve.return_value = [make_test_context([make_test_span(n=0)])]
    mock_legacy_store = Mock()
    mock_legacy_store.search_hybrid.return_value = []
    mock_legacy_store.collection = "first_person_v9"

    pipeline = FirstPersonPipeline(
        store=mock_legacy_store,
        serene_mind_engine=Mock(),
        context_store=mock_context_store,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    pipeline.execute(
        query="Tell me something",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=True,
    )

    mock_context_store.retrieve.assert_not_called()
    mock_legacy_store.search_hybrid.assert_called_once()


def test_terminal_flag_blocks_legacy_fallthrough(monkeypatch):
    """v10-only serving: with the terminal flag on, a question the harness cannot
    answer abstains and the legacy (v8) store is never searched."""
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", True)
    mock_ctx_store = Mock()
    mock_ctx_store.retrieve.return_value = []
    mock_legacy_store = Mock()
    mock_legacy_store.search_hybrid.return_value = []
    mock_legacy_store.collection = "first_person_v8"

    pipeline = FirstPersonPipeline(
        store=mock_legacy_store,
        serene_mind_engine=Mock(),
        context_store=mock_ctx_store,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="Tell me something",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=True,
    )

    assert result.status == "abstained"
    assert result.abstain_reason == "no_verified_clips"
    assert result.citations == []
    mock_legacy_store.search_hybrid.assert_not_called()


def test_terminal_flag_is_off_by_default():
    assert settings.model_fields["first_person_context_terminal_enabled"].default is False


def test_harness_does_not_stitch_succeeding_span_after_decision(monkeypatch):
    """A cutoff-looking span is not widened after the harness decision."""
    mock_ctx_store = Mock()
    s1 = make_test_span(
        n=0,
        text="Inner peace begins with deep understanding. For what is a beautiful state? What is this transformed consciousness we are talking about?",
        video_id="vid_test_1",
        guru_id="krishnaji",
    )
    s2 = make_test_span(
        n=1,
        text="A beautiful state is a state of calm, a state of connection, where you are not lost in the endless noise of self-centered thought.",
        start_ms=s1.end_ms + 100,
        end_ms=s1.end_ms + 15000,
        video_id=s1.video_id,
        guru_id=s1.guru_id,
    )

    mock_ctx_store.retrieve.return_value = [make_test_context([s1])]
    mock_ctx_store.fetch_succeeding_span.return_value = s2

    pipeline = FirstPersonPipeline(
        store=Mock(), serene_mind_engine=Mock(), context_store=mock_ctx_store
    )
    pipeline._serene_mind.assess_distress.return_value = None
    pipeline._store.search_hybrid.return_value = []

    res = pipeline.execute(
        query="What is a beautiful state?",
        query_dense_vector=[0.1] * 1024,
        teacher_id=s1.guru_id,
        cache_bypass=True,
    )

    mock_ctx_store.fetch_succeeding_span.assert_not_called()
    assert s1.verbatim_text in res.answer_text
    assert s2.verbatim_text not in res.answer_text


def _rejected_antecedent_fixture():
    """Return a first-child opener whose typed predecessor lookup is refused."""
    predecessor, opener, context = _cross_parent_serving_context()
    context_store = Mock()
    context_store.retrieve.return_value = [context]
    # The opener is a genuine first child with an antecedent pointer, but the
    # store refuses to issue the validated cross-parent edge.  The pipeline must
    # not let the failed fp-context candidate leak into either final response.
    context_store.fetch_preceding_span.return_value = None

    legacy_text = "Legacy fallback evidence remains deterministic and source-verbatim."
    legacy_clip = {
        "point_id": "legacy-antecedent-fallback-1",
        "video_id": "legacyAntecedent01",
        "start_ms": 12000,
        "end_ms": 18000,
        "speaker": "Sri Krishnaji",
        "guru_id": "krishnaji",
        "teacher_id": "krishnaji",
        "title": "Deterministic legacy fallback fixture",
        "source_url": "https://www.youtube.com/watch?v=legacyAntecedent01",
        "verbatim_text": legacy_text,
        "transcript_hash": hashlib.sha256(legacy_text.encode("utf-8")).hexdigest(),
        "rights_cleared": True,
        "domain_rights_status": "licensed",
        "first_person_eligible": True,
        "speaker_verified": True,
        "voice_verification_method": "synthetic-test-fixture",
        "passage_dense": [0.1] * 1024,
        "caption_status": "auto_transcript",
    }
    legacy_store = Mock()
    legacy_store.search_hybrid.return_value = [legacy_clip]
    legacy_store.collection = "first_person_v8"
    return predecessor, opener, context_store, legacy_store, legacy_clip


def test_terminal_rejected_antecedent_abstains_without_legacy_or_fp_leak(monkeypatch):
    """Terminal fp-context serving abstains when its first-child predecessor is refused."""
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", True)
    predecessor, opener, context_store, legacy_store, _legacy_clip = _rejected_antecedent_fixture()
    pipeline = FirstPersonPipeline(
        store=legacy_store,
        serene_mind_engine=Mock(),
        context_store=context_store,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="What is awareness?",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=True,
    )

    context_store.fetch_preceding_span.assert_called_once_with(opener)
    assert result.status == "abstained"
    assert result.abstain_reason == "no_verified_clips"
    assert result.citations == []
    assert result.fp_served is False
    assert opener.verbatim_text not in (result.answer_text or "")
    assert predecessor.verbatim_text not in (result.answer_text or "")
    legacy_store.search_hybrid.assert_not_called()


def test_non_terminal_rejected_antecedent_intentionally_uses_legacy_fallback(monkeypatch):
    """With terminal=False, the same fp-context refusal intentionally falls through to legacy."""
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", False)
    predecessor, opener, context_store, legacy_store, legacy_clip = _rejected_antecedent_fixture()
    pipeline = FirstPersonPipeline(
        store=legacy_store,
        serene_mind_engine=Mock(),
        context_store=context_store,
    )
    pipeline._serene_mind.assess_distress.return_value = None

    # The legacy fixture is deterministic; every availability, integrity,
    # content, safety, hero, and OKF check is mocked so this test cannot use a
    # provider, network, Redis, Qdrant, or Docker service.
    with (
        patch("services.first_person_pipeline._passes_integrity_gate", return_value=True),
        patch("services.first_person_pipeline._passes_content_quality_gate", return_value=True),
        patch(
            "services.first_person_pipeline.first_person_evidence_policy.assess_contextual_safety",
            return_value=Mock(may_serve=True),
        ),
        patch(
            "services.first_person_pipeline.verify_hero_clip",
            return_value={
                "label": "Sri Krishnaji",
                "title": legacy_clip["title"],
                "url": legacy_clip["source_url"] + "&t=12s",
                "start_sec": 12,
                "video_id": legacy_clip["video_id"],
            },
        ),
        patch("services.first_person_pipeline.is_youtube_video_available", return_value=True),
        patch("services.first_person_pipeline.match_okf_entries", return_value=[]),
    ):
        result = pipeline.execute(
            query="What is awareness?",
            query_dense_vector=[0.1] * 1024,
            cache_bypass=True,
        )

    context_store.fetch_preceding_span.assert_called_once_with(opener)
    legacy_store.search_hybrid.assert_called_once()
    assert settings.first_person_context_terminal_enabled is False
    assert result.status == "weak_match"
    assert result.abstain_reason == "none"
    assert result.is_direct_answer is False
    assert result.answer_text == (
        f'"{legacy_clip["verbatim_text"]}"\n— Sri Krishnaji ({legacy_clip["video_id"]}, 12s)'
    )
    assert len(result.citations) == 1
    assert result.citations[0]["provenance_kind"] == "weak_match_fallback"
    assert "source_span_id" not in result.citations[0]
    assert opener.verbatim_text not in result.answer_text
    assert predecessor.verbatim_text not in result.answer_text


def test_editorial_set_selector_is_default_off_and_nonproduction_only(monkeypatch):
    from services.first_person_pipeline import _editorial_set_enabled

    assert settings.model_fields["first_person_editorial_set_selection_enabled"].default is False
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    monkeypatch.setattr(settings, "first_person_editorial_set_selection_enabled", True)
    monkeypatch.setattr(settings, "is_production", True)
    assert _editorial_set_enabled() is False

    monkeypatch.setattr(settings, "is_production", False)
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", False)
    assert _editorial_set_enabled() is False

    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    assert _editorial_set_enabled() is True
