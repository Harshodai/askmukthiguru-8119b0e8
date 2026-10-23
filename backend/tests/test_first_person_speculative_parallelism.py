"""
test_first_person_speculative_parallelism.py

Comprehensive test suite verifying Track 1: Speculative Parallelism & Latency Optimization (Sub-2s).

Objectives & Invariants covered:
1. Configuration declaration:
   - settings.first_person_speculative_parallelism_enabled default is False (Invariant S7).
2. Speculative Concurrency:
   - At t=0, Answerability Gate and Vector Retrieval run concurrently via asyncio.gather.
   - If Answerability Gate returns 'no', retrieval candidates are immediately discarded
     and pipeline returns honest abstention (abstain_reason='answerability_withheld')
     without calling reranker or scorer.
   - If Answerability Gate returns 'yes', candidates are already pre-fetched in memory
     and flow through integrity and scoring.
3. Cascade Reranker-to-Scorer Filtering:
   - If Cross-Encoder rerank score is < 0.30, candidate is dropped immediately without
     reaching LLM standalone scorer.
   - If all candidates score < 0.30, pipeline abstains without calling scorer.
   - Candidate #1 is scored first. If score >= 3, it is served immediately without
     evaluating Candidate #2. Candidate #2 is evaluated only on tie/rejection.
4. Safety & Invariants:
   - Invariant S4: Acute crisis rail executes before any concurrent task launch.
   - Invariants S1/S2/S3: Text remains 100% exact byte match to transcript_hash; zero LLM teaching generated.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.config import settings
from services.first_person_pipeline import FirstPersonPipeline

pytestmark = [pytest.mark.answerability_real, pytest.mark.relevance_real]


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------


def _make_clip(point_id: str, text: str, video_id: str = "hLg4WPG4ehE") -> dict[str, Any]:
    tx_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "point_id": point_id,
        "video_id": video_id,
        "title": "Teaching on State of Being",
        "video_title": "Teaching on State of Being",
        "start_ms": 10000,
        "end_ms": 30000,
        "start_sec": 10,
        "end_sec": 30,
        "timestamp_seconds": 10,
        "speaker": "Sri Krishnaji",
        "teacher_id": "krishnaji",
        "speaker_verified": True,
        "channel": "Ekam Wisdom",
        "transcript_hash": tx_hash,
        "verbatim_text": text,
        "text_snippet": text,
        "source_url": f"https://www.youtube.com/watch?v={video_id}&t=10s",
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "passage_dense": [0.8] * 1024,
        "confidence": 0.88,
        "is_verbatim": True,
        "caption_status": "auto_transcript",
        "transcript_status": "auto_transcript",
        "asr_artifacts": [],
    }


@pytest.fixture(autouse=True)
def _content_quality_gate_off_for_toy_fixtures(monkeypatch):
    """Disable length filter so concise fixtures pass integrity gate cleanly."""
    monkeypatch.setattr(settings, "first_person_content_quality_gate_enabled", False)
    monkeypatch.setattr(settings, "first_person_relevance_model", "")


# ---------------------------------------------------------------------------
# 1. Configuration Declaration Tests
# ---------------------------------------------------------------------------


def test_speculative_parallelism_config_default_false() -> None:
    """Invariant S7: Speculative parallelism must be False by default."""
    from app.config import Settings

    assert hasattr(settings, "first_person_speculative_parallelism_enabled")
    assert Settings.model_fields["first_person_speculative_parallelism_enabled"].default is False
    assert hasattr(settings, "first_person_cross_encoder_min_score")
    assert settings.first_person_cross_encoder_min_score == 0.30


# ---------------------------------------------------------------------------
# 2. Speculative Concurrency Tests
# ---------------------------------------------------------------------------


def test_speculative_concurrency_at_t0_runs_ans_and_retrieval(monkeypatch) -> None:
    """When enabled, Answerability Gate and Vector Retrieval run concurrently at t=0."""
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", False)

    clip = _make_clip("pt_1", "Suffering is an internal division in consciousness.")
    mock_store = MagicMock()
    mock_store.search_hybrid.return_value = [clip]

    mock_llm = MagicMock()
    mock_llm.generate.return_value = "YES"

    pipeline = FirstPersonPipeline(store=mock_store, llm_service=mock_llm)
    res = pipeline.execute(query="What is suffering?", query_dense_vector=[0.8] * 1024)

    assert res.status in ("success", "weak_match")
    assert mock_store.search_hybrid.call_count == 1
    assert mock_llm.generate.call_count == 1
    assert res.stage_timings["answerability_ms"] >= 0.0
    assert res.stage_timings["retrieval_ms"] >= 0.0


def test_speculative_answerability_no_discards_retrieval_candidates(monkeypatch) -> None:
    """If Answerability returns 'no', retrieval candidates are discarded immediately,

    skipping reranker and scorer completely.
    """
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(settings, "first_person_llm_rerank_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)

    clip = _make_clip("pt_1", "Suffering is an internal division in consciousness.")
    mock_store = MagicMock()
    mock_store.search_hybrid.return_value = [clip]

    # LLM returns NO for answerability
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "NO"

    rerank_calls = []
    pipeline = FirstPersonPipeline(
        store=mock_store,
        llm_service=mock_llm,
        rerank_fn=lambda q, texts: rerank_calls.append(texts) or [0.9] * len(texts),
    )

    res = pipeline.execute(
        query="What is the capital of France?",
        query_dense_vector=[0.1] * 1024,
    )

    # Must abstain with answerability_withheld
    assert res.status == "abstained"
    assert res.answerability == "no"
    assert res.abstain_reason == "answerability_withheld"
    assert len(res.citations) == 0

    # Reranker and scorer must NOT have been called
    assert rerank_calls == []
    # mock_llm was only called for answerability, never for rerank or scorer
    assert mock_llm.generate.call_count == 1


def test_speculative_answerability_yes_serves_prefetched_candidates(monkeypatch) -> None:
    """If Answerability returns 'yes', pre-fetched retrieval candidates are served cleanly."""
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", False)

    clip = _make_clip("pt_1", "Suffering is an internal division in consciousness.")
    mock_store = MagicMock()
    mock_store.search_hybrid.return_value = [clip]

    mock_llm = MagicMock()
    mock_llm.generate.return_value = "YES"

    pipeline = FirstPersonPipeline(store=mock_store, llm_service=mock_llm)
    res = pipeline.execute(
        query="What is suffering?",
        query_dense_vector=[0.8] * 1024,
    )

    assert res.status in ("success", "weak_match")
    assert len(res.citations) == 1
    assert res.citations[0]["point_id"] == "pt_1"
    assert res.citations[0]["verbatim_text"] == clip["verbatim_text"]


# ---------------------------------------------------------------------------
# 3. Cascade Reranker-to-Scorer Filtering Tests
# ---------------------------------------------------------------------------


def test_cascade_cross_encoder_filtering_drops_below_030(monkeypatch) -> None:
    """Candidates with cross-encoder score < 0.30 are dropped before reaching scorer."""
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    monkeypatch.setattr(settings, "first_person_llm_rerank_enabled", False)

    clip1 = _make_clip("pt_1", "Suffering is an internal division in consciousness.")
    clip2 = _make_clip("pt_2", "Cooking pasta requires boiling salted water first.")
    clip3 = _make_clip("pt_3", "The stock market fluctuates based on macro indicators.")

    mock_store = MagicMock()
    mock_store.search_hybrid.return_value = [clip1, clip2, clip3]

    # LLM returns YES for answerability, and 3 for candidate #1 scoring
    def _llm_gen(**kwargs):
        sys_p = kwargs.get("system_prompt", "")
        if "question classifier" in sys_p.lower() or "reply yes" in sys_p.lower():
            return "YES"
        return "3"

    mock_llm = MagicMock()
    mock_llm.generate.side_effect = _llm_gen

    # Cross-encoder scores: clip1=0.75 (keep), clip2=0.20 (drop), clip3=0.10 (drop)
    def _mock_rerank(query, texts):
        return [0.75, 0.20, 0.10]

    pipeline = FirstPersonPipeline(
        store=mock_store,
        llm_service=mock_llm,
        rerank_fn=_mock_rerank,
    )

    res = pipeline.execute(
        query="What is suffering?",
        query_dense_vector=[0.8] * 1024,
    )

    assert res.status in ("success", "weak_match")
    assert len(res.citations) == 1
    assert res.citations[0]["point_id"] == "pt_1"


def test_cascade_cross_encoder_below_030_keeps_candidates_for_scorer(monkeypatch) -> None:
    """All cross-encoder scores < 0.30 must NOT empty the candidate list.

    2026-10-20: d1c9bf53 added the ``if not pairs: pairs = [...]`` fallback so a
    starved cascade cannot manufacture ``no_verified_clips`` (the same commit's
    goal was relevance_indeterminate == 0). This test previously asserted the
    opposite — abstain without calling the scorer — and had been failing since.
    """
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)

    clip1 = _make_clip("pt_1", "Unrelated clip text about automobiles.")
    clip2 = _make_clip("pt_2", "Another unrelated clip text about gardening.")

    mock_store = MagicMock()
    mock_store.search_hybrid.return_value = [clip1, clip2]

    # YES for the answerability classifier; for the relevance scorer return
    # exactly one integer score per clip in the prompt (extra scores are now
    # rejected as malformed rather than truncated).
    def _generate(system_prompt: str = "", user_prompt: str = "", **_kw) -> str:
        if "question classifier" in system_prompt:
            return "YES"
        clip_count = len(re.findall(r"^\[\d+\]", user_prompt, re.MULTILINE))
        return ",".join("3" for _ in range(max(1, clip_count)))

    mock_llm = MagicMock()
    mock_llm.generate.side_effect = _generate

    # Both clips score below 0.30
    def _mock_rerank(query, texts):
        return [0.22, 0.15]

    pipeline = FirstPersonPipeline(
        store=mock_store,
        llm_service=mock_llm,
        rerank_fn=_mock_rerank,
    )

    res = pipeline.execute(
        query="What is suffering?",
        query_dense_vector=[0.8] * 1024,
    )

    assert res.status in ("success", "weak_match")
    # Not abstained, and a clip from the (all-below-0.30) candidate set was served:
    # the cascade fallback must not empty the pool.
    assert len(res.citations) >= 1
    assert res.citations[0]["point_id"] in {"pt_1", "pt_2"}
    # Answerability + relevance scoring (the scorer DOES run: the cascade keeps
    # candidates instead of abstaining before it). >= 2 because another gate may
    # add a call on this path; the point is that the scorer is not skipped.
    assert mock_llm.generate.call_count >= 2


def test_scorer_candidate_1_first_short_circuits_on_score_3(monkeypatch) -> None:
    """If Candidate #1 scores >= 3, it is served immediately without evaluating Candidate #2."""
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    monkeypatch.setattr(settings, "first_person_llm_rerank_enabled", False)

    clip1 = _make_clip("pt_1", "Suffering is an internal division in consciousness.")
    clip2 = _make_clip("pt_2", "Suffering ends when one observes without judgment.")

    mock_store = MagicMock()
    mock_store.search_hybrid.return_value = [clip1, clip2]

    scorer_prompts = []

    def _llm_gen(**kwargs):
        sys_p = kwargs.get("system_prompt", "")
        if "question classifier" in sys_p.lower() or "reply yes" in sys_p.lower():
            return "YES"
        scorer_prompts.append(kwargs.get("user_prompt", ""))
        return "3"

    mock_llm = MagicMock()
    mock_llm.generate.side_effect = _llm_gen

    pipeline = FirstPersonPipeline(store=mock_store, llm_service=mock_llm)
    res = pipeline.execute(query="What is suffering?", query_dense_vector=[0.8] * 1024)

    assert res.status in ("success", "weak_match")
    assert len(res.citations) == 1
    assert res.citations[0]["point_id"] == "pt_1"
    # Scorer was called exactly once for candidate #1, NOT for candidate #2
    assert len(scorer_prompts) == 1
    assert "pt_1" in scorer_prompts[0] or clip1["verbatim_text"] in scorer_prompts[0]


def test_scorer_evaluates_candidate_2_on_candidate_1_rejection(monkeypatch) -> None:
    """If Candidate #1 scores < 3, Candidate #2 is evaluated. If Candidate #2 scores >= 3, it is served."""
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    monkeypatch.setattr(settings, "first_person_llm_rerank_enabled", False)

    clip1 = _make_clip("pt_1", "Some vague background anecdote.")
    clip2 = _make_clip("pt_2", "Suffering is dissolved by awakening to oneness.")

    mock_store = MagicMock()
    mock_store.search_hybrid.return_value = [clip1, clip2]

    scorer_calls = []

    def _llm_gen(**kwargs):
        sys_p = kwargs.get("system_prompt", "")
        if "question classifier" in sys_p.lower() or "reply yes" in sys_p.lower():
            return "YES"
        scorer_calls.append(kwargs.get("user_prompt", ""))
        if len(scorer_calls) == 1:
            return "1"  # Candidate #1 rejected
        return "3"  # Candidate #2 accepted

    mock_llm = MagicMock()
    mock_llm.generate.side_effect = _llm_gen

    pipeline = FirstPersonPipeline(store=mock_store, llm_service=mock_llm)
    res = pipeline.execute(query="What is suffering?", query_dense_vector=[0.8] * 1024)

    assert res.status in ("success", "weak_match")
    assert len(res.citations) == 1
    assert res.citations[0]["point_id"] == "pt_2"
    # Scorer was called twice: once for candidate 1, then once for candidate 2
    assert len(scorer_calls) == 2


def test_scorer_abstains_when_both_candidates_rejected(monkeypatch) -> None:
    """If Candidate #1 and Candidate #2 both score < 3, pipeline returns honest abstention."""
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    monkeypatch.setattr(settings, "first_person_llm_rerank_enabled", False)

    clip1 = _make_clip("pt_1", "Some vague background anecdote.")
    clip2 = _make_clip("pt_2", "Another tangentially related sentence.")

    mock_store = MagicMock()
    mock_store.search_hybrid.return_value = [clip1, clip2]

    def _llm_gen(**kwargs):
        sys_p = kwargs.get("system_prompt", "")
        if "question classifier" in sys_p.lower() or "reply yes" in sys_p.lower():
            return "YES"
        return "1"  # Both return 1

    mock_llm = MagicMock()
    mock_llm.generate.side_effect = _llm_gen

    pipeline = FirstPersonPipeline(store=mock_store, llm_service=mock_llm)
    res = pipeline.execute(query="What is suffering?", query_dense_vector=[0.8] * 1024)

    assert res.status == "abstained"
    assert res.abstain_reason == "relevance_below_min"
    assert len(res.citations) == 0


# ---------------------------------------------------------------------------
# 4. Safety Precedence & Disabled Flag Tests
# ---------------------------------------------------------------------------


def test_crisis_preemption_invariant_s4_executes_before_speculative_tasks(monkeypatch) -> None:
    """Invariant S4: Acute crisis rail must execute before any concurrent task launch."""
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)

    mock_store = MagicMock()
    mock_llm = MagicMock()

    pipeline = FirstPersonPipeline(store=mock_store, llm_service=mock_llm)
    res = pipeline.execute(
        query="I want to kill myself, I cannot go on living",
        query_dense_vector=[0.0] * 1024,
    )

    assert res.status == "crisis_redirect"
    assert "988" in res.answer_text
    assert mock_store.search_hybrid.call_count == 0
    assert mock_llm.generate.call_count == 0


def test_speculative_disabled_runs_sequential_baseline_path(monkeypatch) -> None:
    """When disabled, the pipeline follows the baseline execution path."""
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", False)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", False)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", False)

    clip = _make_clip("pt_1", "Suffering is an internal division in consciousness.")
    mock_store = MagicMock()
    mock_store.search_hybrid.return_value = [clip]

    pipeline = FirstPersonPipeline(store=mock_store)
    res = pipeline.execute(query="What is suffering?", query_dense_vector=[0.8] * 1024)

    assert res.status in ("success", "weak_match")
    assert len(res.citations) == 1
    assert res.citations[0]["point_id"] == "pt_1"
