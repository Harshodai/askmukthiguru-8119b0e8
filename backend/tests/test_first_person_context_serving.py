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
from unittest.mock import Mock, patch

import pytest
from qdrant_client import QdrantClient

from app.config import settings
from domain.first_person_context import (
    AnswerRole,
    BoundaryStatus,
    CompletenessStatus,
    ParentContext,
    ParentUnit,
    ProvenanceKind,
    SourceSpan,
    SpeakerRole,
    clip_text_hash,
    make_source_span_id,
)
from services.first_person_context_harness import (
    reset_harness_metrics,
)
from services.first_person_pipeline import FirstPersonPipeline

TEXT_ONE = (
    "Suffering is not a punishment that existence hands to you; it is a call to awaken "
    "to the resistance you carry inside yourself every single day."
)
TEXT_TWO = (
    "When you stop fighting that pain and simply stay present with it, the mind becomes "
    "quiet and the heart opens without any effort at all."
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
        "source_transcript_text": span_text,
        "verbatim_text": span_text,
        "transcript_hash": span_hash,
        "source_text_hash": clip_text_hash(span_text),
        "boundary_status": BoundaryStatus.VERIFIED,
        "completeness_status": CompletenessStatus.COMPLETE,
        "rights_cleared": True,
        "caption_status": "auto_transcript",
        "provenance_kind": ProvenanceKind.SPEECH_TURN_SPAN,
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
        "answer_role": AnswerRole.DIRECT,
    }
    data.update(overrides)
    return SourceSpan(**data)


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
    # The serve-time integrity gate calls YouTube availability (FI-16). These
    # tests are about harness wiring, not video liveness, and fixture video ids
    # are synthetic, so keep the check out of the network.
    monkeypatch.setattr(
        "services.first_person_pipeline.is_youtube_video_available", lambda _vid: True
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
    span2 = make_test_span(n=1, text=TEXT_TWO)
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
    assert len(result.citations) == 2
    assert result.citations[0]["start_ms"] == span1.start_ms
    assert result.citations[1]["start_ms"] == span2.start_ms
    assert result.citations[1]["label"] == "Later in this discourse"
    assert len(result.audio_playback_clips) == 2


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


def test_selector_integration(monkeypatch):
    """Phase D8 selector is consulted when enabled and its span order is honored."""
    monkeypatch.setattr(settings, "first_person_context_selector_enabled", True)

    span1 = make_test_span(n=0, text=TEXT_ONE)
    span2 = make_test_span(n=1, text=TEXT_TWO)
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
    def fake(query, clips, llm, loop=None, token_sink=None, scores_out=None):
        assert clips[0]["verbatim_text"] == TEXT_ONE
        scores_out[:] = [2]
        return None

    result = _run_with_scorer(monkeypatch, fake)
    assert result.answer_text != TEXT_ONE


def test_harness_answer_scored_at_min_is_served(monkeypatch):
    def fake(query, clips, llm, loop=None, token_sink=None, scores_out=None):
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
