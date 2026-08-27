from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingest.quality_gate import DataQualityGate
from rag.states import GraphState
from services.doctrine_service import DoctrineService
from services.okf_quality_filter import OKFQualityFilter
from tasks.ingest_tasks import ingest_playlist, playlist_complete


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    # Mock return for quality score grading
    llm.generate.return_value = '{"score": 85, "reasons": ["Excellent educational content"]}'
    return llm


@pytest.fixture
def mock_supabase():
    client = MagicMock()
    # Mock insert/execute returns
    mock_execute = MagicMock()
    mock_execute.data = [{"id": "mock-job-id"}]
    client.table.return_value.insert.return_value.execute.return_value = mock_execute
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_execute
    )
    client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        mock_execute
    )
    return client


@pytest.mark.asyncio
async def test_data_quality_gate_pass(mock_llm, mock_supabase):
    gate = DataQualityGate(
        llm_service=mock_llm, supabase_client=mock_supabase, quality_threshold=70, enabled=True
    )
    long_spiritual_text = (
        "This is a highly spiritual teaching about meditation, focus, and inner peace. "
        "Let us settle into quiet observation and find our true alignment. "
        "We want to feel oneness with all that is, releasing any suffering states "
        "and resting in a beautiful state of consciousness."
    )
    result = await gate.run(long_spiritual_text, source_url="https://youtube.com/watch?v=123")
    assert result.passed is True
    assert result.score == 91
    assert "reasons" in result.__dict__


@pytest.mark.asyncio
async def test_data_quality_gate_fail_repetition(mock_llm, mock_supabase):
    gate = DataQualityGate(
        llm_service=mock_llm, supabase_client=mock_supabase, quality_threshold=70, enabled=True
    )
    # Text with high repetition to trigger the n-gram filter (deterministic fail)
    repetitive_text = (
        "meditation peace meditation peace meditation peace meditation peace meditation peace "
        "meditation peace meditation peace meditation peace meditation peace meditation peace "
        "meditation peace meditation peace meditation peace meditation peace meditation peace "
        "meditation peace meditation peace meditation peace meditation peace meditation peace"
    )
    result = await gate.run(repetitive_text, source_url="https://youtube.com/watch?v=123")
    assert result.passed is False
    assert result.score == 0
    assert any("repetitive" in r.lower() for r in result.reasons)


@pytest.mark.asyncio
async def test_okf_quality_filter():
    # Valid entry — provenance is mandatory: every OKF claim is cited to the seeker.
    valid, reason = OKFQualityFilter.validate_entry(
        {
            "title": "Beautiful State",
            "type": "concept",
            "source": "Beautiful State — Sri Preethaji (YouTube TqxxCYnAxo8)",
            "body": "This is a very long body containing teachings of Sri Preethaji that exceeds one hundred characters easily.",
        }
    )
    assert valid is True, reason

    # Invalid entry
    invalid, reason = OKFQualityFilter.validate_entry(
        {"title": "", "type": "concept", "body": "Short body"}
    )
    assert invalid is False

    # Uncitable entry — no source means format_final_answer cannot attribute it.
    uncitable, reason = OKFQualityFilter.validate_entry(
        {
            "title": "Sacred Secrets",
            "type": "teaching",
            "body": "A sufficiently long body about the teachings of Sri Preethaji and Sri Krishnaji, well past one hundred characters.",
        }
    )
    assert uncitable is False and "source" in reason.lower()

    # Extraction artifact — the LLM's own prompt commentary must never be served as doctrine.
    leaked, reason = OKFQualityFilter.validate_entry(
        {
            "title": "Sacred Secrets",
            "type": "teaching",
            "source": "auto-extracted from Qdrant (6 chunks)",
            "body": "The user wants me to analyze a spiritual teaching and list the top 3-5 distinct topics discussed in this long text.",
        }
    )
    assert leaked is False and "leakage" in reason.lower()


@pytest.mark.asyncio
async def test_doctrine_service(mock_supabase):
    # Mock select return
    mock_execute = MagicMock()
    mock_execute.data = [
        {
            "synonyms_json": {
                "Beautiful State": ["beautiful state", "blissful state"],
                "Soul Sync": ["soul sync", "meditation sync"],
            },
            "canonical_terms": ["Beautiful State", "Soul Sync"],
        }
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_execute
    )

    service = DoctrineService(supabase_client=mock_supabase)

    # Test query enhancement
    enhanced = await service.inject_doctrine_keywords(
        "I want to experience the blissful state", "preethaji_krishnaji"
    )
    assert "Beautiful State" in enhanced

    # If already contains canonical, do not double-inject
    enhanced_dup = await service.inject_doctrine_keywords(
        "I want to experience the Beautiful State", "preethaji_krishnaji"
    )
    assert enhanced_dup.strip() == "I want to experience the Beautiful State"


@patch("tasks.ingest_tasks.orchestrate_ingestion")
@patch("ingest.youtube_loader.get_playlist_video_urls")
def test_ingest_playlist_chord(mock_get_urls, mock_orchestrate, mock_supabase):
    mock_get_urls.return_value = [
        {"url": "https://youtube.com/watch?v=v1", "title": "Video 1"},
        {"url": "https://youtube.com/watch?v=v2", "title": "Video 2"},
    ]

    with (
        patch("celery.app.task.Task.update_state"),
        patch("celery.chord", return_value=MagicMock()),
        patch("tasks.ingest_tasks.update_job_progress"),
        patch("tasks.ingest_tasks.settings") as mock_settings,
        patch("supabase.create_client") as mock_create_client,
    ):
        mock_settings.supabase_url = "https://example.supabase.co"
        mock_settings.supabase_service_key = "test-service-key"
        mock_settings.supabase_key = "test-anon-key"
        mock_create_client.return_value = mock_supabase

        # Call ingest_playlist
        res = ingest_playlist(
            "https://youtube.com/playlist?list=123", tags=["spiritual"], job_id="parent-job"
        )

        assert res["status"] == "queued"
        assert res["video_count"] == 2

        # Verify Supabase client was called to create child jobs
        assert mock_supabase.table.call_count > 0


def test_playlist_complete(mock_supabase):
    results = [
        {"status": "success", "indexing": {"count": 12}},
        {"status": "success", "indexing": {"count": 8}},
        {"status": "rejected"},
    ]

    with (
        patch("tasks.ingest_tasks.update_job_progress") as mock_update,
        patch("tasks.ingest_tasks.post_ingestion_maintenance.delay") as mock_maintenance,
    ):
        res = playlist_complete(
            results,
            "https://youtube.com/playlist?list=123",
            parent_job_id="parent-job",
            total_count=3,
        )
        assert res["status"] == "success"
        assert res["success"] == 2
        assert res["rejected"] == 1
        assert res["chunks_indexed"] == 20

        # Verify parent job completion update
        mock_update.assert_called_once_with(
            "parent-job", "completed", progress_pct=100, chunks_indexed=20, error_message=None
        )
        mock_maintenance.assert_called_once_with(trigger="playlist_complete")


class _WordOverlapScorer:
    """Stand-in faithfulness scorer: score = answer-word overlap with context.

    Mirrors LettuceDetectService.score_faithfulness's contract without needing
    the real embedder in a unit test.
    """

    def score_faithfulness(self, query, context, answer):
        import re

        ctx = set(re.findall(r"\w+", context.lower()))
        ans = set(re.findall(r"\w+", answer.lower()))
        return {"score": len(ans & ctx) / max(1, len(ans))}


def test_gate_summary_faithfulness_drops_unsupported_summary():
    from ingest.quality_gate import gate_summary_faithfulness

    sources = [
        "Surrender is the path to the beautiful state taught at Ekam.",
        "In the beautiful state the mind is calm, connected, and free of suffering.",
    ]
    scorer = _WordOverlapScorer()

    supported, s_ok = gate_summary_faithfulness(
        "Surrender leads to the calm, connected beautiful state.", sources, scorer
    )
    fabricated, s_bad = gate_summary_faithfulness(
        "Krishnaji guarantees followers wealth, fame, and eternal youth.",
        sources,
        scorer,
    )

    assert supported is True, f"supported summary should pass (score={s_ok})"
    assert fabricated is False, f"fabrication should be gated out (score={s_bad})"
    assert s_bad < s_ok


@pytest.mark.asyncio
async def test_llm_quality_timeout_is_explicit_unknown():
    from ingest.quality_gate import LLMQualityScorer

    class TimeoutLLM:
        async def generate(self, **kwargs):
            raise TimeoutError()

    score, reasons = await LLMQualityScorer(TimeoutLLM()).score(
        "A sufficiently long spiritual teaching about consciousness and presence."
    )
    assert score == 0
    assert any(reason.startswith("QUALITY_UNKNOWN:") for reason in reasons)


@pytest.mark.asyncio
async def test_quality_gate_unknown_never_passes():
    from ingest.quality_gate import DataQualityGate

    class FailingLLM:
        async def generate(self, **kwargs):
            raise RuntimeError("provider unavailable")

    text = (
        "This is a sufficiently long spiritual teaching about consciousness, presence, "
        "meditation, compassion, and the beautiful state of being. It describes how "
        "attention, surrender, gratitude, and inner stillness can transform suffering "
        "into a more connected and peaceful way of living for a seeker."
    )
    result = await DataQualityGate(llm_service=FailingLLM()).run(text)
    assert result.passed is False
    assert any(reason.startswith("QUALITY_UNKNOWN:") for reason in result.reasons)


def test_llm_quality_malformed_json_is_explicit_unknown():
    from ingest.quality_gate import LLMQualityScorer

    score, reasons = LLMQualityScorer(object())._parse_json_response("not-json")
    assert score == 0
    assert any(reason.startswith("QUALITY_UNKNOWN:") for reason in reasons)


@pytest.mark.asyncio
async def test_llm_quality_scorer_retries_past_transient_provider_degradation():
    """Regression: a circuit-breaker-open fallback string from openrouter_service
    or nim_service used to be fed straight to the JSON parser and permanently
    quarantined as QUALITY_UNKNOWN -- observed live to cause 370 of 428
    ingestion rejections in one run when the breaker tripped mid-run (2026-08-27).
    A transient degradation should be retried, not treated as a permanent
    parse failure, since circuit breakers self-recover on a timer.
    """
    from ingest.quality_gate import LLMQualityScorer

    calls = {"n": 0}

    class RecoveringLLM:
        async def generate(self, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return (
                    "I'm here and listening. However, I'm experiencing a temporary "
                    "connection issue with my backend services. Please try again shortly."
                )
            return '{"score": 85, "verdict": "PASS", "is_spiritual": true, "coherence": "high", "reasons": []}'

    scorer = LLMQualityScorer(RecoveringLLM())
    scorer._max_attempts = 3
    import ingest.quality_gate as qg

    async def no_sleep(_seconds):
        return None

    original_sleep = qg.asyncio.sleep
    qg.asyncio.sleep = no_sleep
    try:
        score, reasons = await scorer.score(
            "A sufficiently long spiritual teaching about consciousness and presence."
        )
    finally:
        qg.asyncio.sleep = original_sleep

    assert calls["n"] == 2, "should have retried once after the degraded response"
    assert score == 85
    assert reasons == []


@pytest.mark.asyncio
async def test_llm_quality_scorer_quarantines_after_persistent_degradation():
    """If the provider stays degraded across every retry, quarantine as
    UNKNOWN with a distinct reason -- must not silently pass, and must not
    be confused with a genuine malformed-JSON response.
    """
    from ingest.quality_gate import LLMQualityScorer

    class AlwaysDegradedLLM:
        async def generate(self, **kwargs):
            return (
                "I'm currently experiencing a temporary connectivity issue with my "
                "knowledge base. Please try your question again in a few moments. "
                "I'll be happy to help you once I'm fully connected."
            )

    scorer = LLMQualityScorer(AlwaysDegradedLLM())
    import ingest.quality_gate as qg

    async def no_sleep(_seconds):
        return None

    original_sleep = qg.asyncio.sleep
    qg.asyncio.sleep = no_sleep
    try:
        score, reasons = await scorer.score(
            "A sufficiently long spiritual teaching about consciousness and presence."
        )
    finally:
        qg.asyncio.sleep = original_sleep

    assert score == 0
    assert any("degraded" in reason.lower() for reason in reasons)


@pytest.mark.asyncio
async def test_cove_thresholds_and_verdicts(monkeypatch):
    from rag.nodes.verification import _cove_subquestion_check

    class MockOllama:
        def __init__(self, answer_yes_count=2, total_sq=3):
            self.answer_yes_count = answer_yes_count
            self.total_sq = total_sq
            self.call_idx = 0

        async def generate(self, system_prompt, user_prompt, **kwargs):
            if "factual verification sub-questions" in system_prompt:
                return "Sub question 1?\nSub question 2?\nSub question 3?"
            # For verification answers
            self.call_idx += 1
            if self.call_idx <= self.answer_yes_count:
                return "yes, supported"
            return "no, not mentioned"

    # Test supported verdict (ratio 3/3 >= 0.8)
    ollama_full = MockOllama(answer_yes_count=3, total_sq=3)
    res_full = await _cove_subquestion_check("Q", "A", "Context", ollama_full)
    assert res_full["passed"] is True
    assert res_full["verdict"] == "supported"
    assert res_full["ratio"] == 1.0

    # Test partially_supported verdict (ratio 2/3 = 0.67, >= 0.5 and < 0.8)
    ollama_partial = MockOllama(answer_yes_count=2, total_sq=3)
    res_partial = await _cove_subquestion_check("Q", "A", "Context", ollama_partial)
    assert res_partial["passed"] is True
    assert res_partial["verdict"] == "partially_supported"
    assert 0.65 < res_partial["ratio"] < 0.7

    # Test unsupported verdict (ratio 1/3 = 0.33, < 0.5)
    ollama_unsupported = MockOllama(answer_yes_count=1, total_sq=3)
    res_unsupported = await _cove_subquestion_check("Q", "A", "Context", ollama_unsupported)
    assert res_unsupported["passed"] is False
    assert res_unsupported["verdict"] == "unsupported"


@pytest.mark.asyncio
async def test_verify_answer_preserves_cove_pass_ratio(monkeypatch):
    """Finding #12: computed CoVe ratio must be preserved in verification state, not forced to 1.0 on pass."""
    import rag.nodes as nodes
    import rag.nodes.verification as verification

    # Force the code path that runs _cove_subquestion_check.
    monkeypatch.setattr(verification.settings, "rag_cove_disabled", False)
    monkeypatch.setattr(verification.settings, "rag_parallel_verify", False)
    monkeypatch.setattr(verification.settings, "cove_compulsory_threshold", 0.5)

    mock_ollama = AsyncMock()
    # First generate: sub-questions; then verification answers.
    mock_ollama.generate.side_effect = [
        "Sub question 1?\nSub question 2?\nSub question 3?",
        "yes",
        "yes",
        "no",
    ]

    mock_embedder = MagicMock()
    mock_qdrant = MagicMock()
    mock_lightrag = MagicMock()
    nodes.init_services(
        ollama=mock_ollama,
        embedder=mock_embedder,
        qdrant=mock_qdrant,
        lightrag=mock_lightrag,
    )
    nodes._llm_gateway = None

    mock_ld = MagicMock()
    mock_ld.score_faithfulness.return_value = {
        "is_faithful": False,
        "score": 0.4,
        "details": "Low faithfulness triggers CoVe.",
        "unsupported_sentences": ["unverified"],
    }
    nodes._lettuce_detect = mock_ld

    state = GraphState(
        question="Q",
        chat_history=[],
        request_id="test-cove-ratio",
        intent="FACTUAL",
        documents=[],
        reranked_docs=[],
        hyde_text=None,
        relevant_docs=[
            {
                "text": "Doctrine text. " * 100,
                "source_url": "url1",
            }
        ],
        grading_reasons=[],
        rewrite_count=0,
        rewritten_query=None,
        sub_queries=["Q"],
        is_complex=True,
        selected_clusters=[],
        hints=[],
        answer="A" * 200,
        citations=[],
        is_faithful=None,
        needs_correction=False,
        reflection_feedback=None,
        verification=None,
        confidence_score=None,
        input_blocked=False,
        output_blocked=False,
        block_reason=None,
        meditation_step=0,
        meditation_response=None,
        final_answer=None,
        error=None,
        context_layers=None,
        citation_reasoning={},
        metrics={},
        user_id=None,
        detected_language="en",
        memory_context="",
        ab_model="primary",
        query_tier="standard",
    )

    result = await nodes.verify_answer(state)

    # CoVe partial pass (2/3) means claim_verification_passed is True, but
    # is_faithful_ld remains False because faithfulness_score < floor, so
    # final passed is False. The key assertion is that the *computed* ratio is
    # preserved in verification state, not forced to 1.0 when claim passes.
    assert result["verification"]["cove_pass_ratio"] == pytest.approx(2 / 3, abs=1e-3)
    assert "0.67" in result["verification"]["details"]
    # Ensure ratio is not the old hard-coded 1.0-for-pass value.
    assert result["verification"]["cove_pass_ratio"] != 1.0


def test_quality_gate_reads_settings_defaults(monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "data_quality_threshold", 65)
    monkeypatch.setattr(app_settings, "data_audit_enabled", True)

    from ingest.quality_gate import DataQualityGate

    gate = DataQualityGate()
    assert gate._threshold == 65
    assert gate._enabled is True
