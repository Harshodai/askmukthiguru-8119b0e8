"""Unit tests for Agentic CRAG Tri-Band Evaluator and RRF k=30 tuning."""

import pytest

from services.crag_evaluator import (
    CRAGAction,
    CRAGDecision,
    CRAGEvaluationResult,
    CRAGEvaluator,
    compute_rrf_tuned,
    evaluate_candidates,
)


def test_crag_evaluator_threshold_validation():
    # Valid default construction
    evaluator = CRAGEvaluator()
    assert evaluator.high_threshold == 0.78
    assert evaluator.low_threshold == 0.45

    # Low threshold greater than high threshold must raise ValueError
    with pytest.raises(ValueError, match="Invalid thresholds"):
        CRAGEvaluator(high_threshold=0.40, low_threshold=0.60)

    # Weights not summing to 1.0 must raise ValueError
    with pytest.raises(ValueError, match="Weights must sum to 1.0"):
        CRAGEvaluator(dense_weight=0.5, margin_weight=0.4)


def test_crag_confidence_formula():
    evaluator = CRAGEvaluator(dense_weight=0.7, margin_weight=0.3)
    # top = 0.8, second = 0.6 => margin = 0.2
    # expected = 0.7 * 0.8 + 0.3 * 0.2 = 0.56 + 0.06 = 0.62
    confidence, dense, margin = evaluator.calculate_confidence(top_score=0.8, second_score=0.6)
    assert pytest.approx(dense, rel=1e-4) == 0.8
    assert pytest.approx(margin, rel=1e-4) == 0.2
    assert pytest.approx(confidence, rel=1e-4) == 0.62


def test_band_1_serve_verbatim():
    evaluator = CRAGEvaluator(high_threshold=0.78, low_threshold=0.45)
    # top = 0.90, second = 0.60 => margin = 0.30
    # confidence = 0.7 * 0.9 + 0.3 * 0.3 = 0.63 + 0.09 = 0.72 -> wait, top=0.92, second=0.40 => margin=0.52
    # 0.7 * 0.92 + 0.3 * 0.52 = 0.644 + 0.156 = 0.80 >= 0.78
    candidates = [
        {"score": 0.92, "verbatim_text": "Suffering is resisting what is.", "teacher": "preethaji"},
        {"score": 0.40, "verbatim_text": "Other text", "teacher": "krishnaji"},
    ]
    res = evaluator.evaluate_candidates(candidates, query="What is suffering?")
    assert res.decision == CRAGDecision.SERVE_VERBATIM
    assert res.confidence_score >= 0.78
    assert res.top_candidate is not None
    assert res.top_candidate["verbatim_text"] == "Suffering is resisting what is."
    assert res.reflection_inquiry is None


def test_band_2_atma_vichara_reflection():
    evaluator = CRAGEvaluator(high_threshold=0.78, low_threshold=0.45)
    # top = 0.70, second = 0.50 => margin = 0.20
    # confidence = 0.7 * 0.70 + 0.3 * 0.20 = 0.49 + 0.06 = 0.55 in [0.45, 0.78)
    candidates = [
        {
            "score": 0.70,
            "verbatim_text": "Inner conflict is natural when divided.",
            "teacher": "krishnaji",
        },
        {"score": 0.50, "verbatim_text": "Peace is stillness.", "teacher": "preethaji"},
    ]
    res = evaluator.evaluate_candidates(candidates, query="Should I quit my job or stay?")
    assert res.decision == CRAGDecision.ATMA_VICHARA_REFLECTION
    assert 0.45 <= res.confidence_score < 0.78
    assert res.reflection_inquiry is not None
    assert len(res.reflection_inquiry) > 20
    # Query stability: same query yields deterministic reflection
    res2 = evaluator.evaluate_candidates(candidates, query="Should I quit my job or stay?")
    assert res2.reflection_inquiry == res.reflection_inquiry


def test_band_3_abstain():
    evaluator = CRAGEvaluator(high_threshold=0.78, low_threshold=0.45)
    # top = 0.35, second = 0.30 => margin = 0.05
    # confidence = 0.7 * 0.35 + 0.3 * 0.05 = 0.245 + 0.015 = 0.26 < 0.45
    candidates = [
        {"score": 0.35, "verbatim_text": "Vague mention of clouds.", "teacher": "preethaji"},
        {"score": 0.30, "verbatim_text": "Another vague fragment.", "teacher": "krishnaji"},
    ]
    res = evaluator.evaluate_candidates(candidates, query="Quantum electrodynamics equations")
    assert res.decision == CRAGDecision.ABSTAIN
    assert res.confidence_score < 0.45
    assert res.reflection_inquiry is None


def test_empty_candidates_fails_closed():
    evaluator = CRAGEvaluator()
    res = evaluator.evaluate_candidates([], query="Any query")
    assert res.decision == CRAGDecision.ABSTAIN
    assert res.confidence_score == 0.0
    assert res.top_candidate is None


def test_single_candidate_evaluation():
    evaluator = CRAGEvaluator()
    # top = 0.85, single candidate => margin = 0.85
    # confidence = 0.7 * 0.85 + 0.3 * 0.85 = 0.85
    candidates = [{"similarity": 0.85, "verbatim_text": "Single clip text"}]
    res = evaluator.evaluate_candidates(candidates)
    assert res.decision == CRAGDecision.SERVE_VERBATIM
    assert pytest.approx(res.confidence_score, rel=1e-4) == 0.85


def test_tuned_rrf_k30_sharper_discrimination():
    vector_rank = ["clip_A", "clip_B", "clip_C"]
    graph_rank = ["clip_A", "clip_D", "clip_B"]

    fused = compute_rrf_tuned([vector_rank, graph_rank], k=30)
    # clip_A is rank 1 in both lists: 1/31 + 1/31 = 2/31 = 0.0645
    # clip_B is rank 2 in vector (1/32) and rank 3 in graph (1/33): 1/32 + 1/33 = 0.0615
    assert fused[0] == "clip_A"
    assert fused[1] == "clip_B"
    assert set(fused) == {"clip_A", "clip_B", "clip_C", "clip_D"}


def test_tuned_rrf_empty_and_single_lists():
    assert compute_rrf_tuned([]) == []
    assert compute_rrf_tuned([[]]) == []
    assert compute_rrf_tuned([["only_one"]], k=30) == ["only_one"]


def test_crag_action_enum_and_aliases():
    assert CRAGAction.SERVE_VERBATIM.value == "SERVE_VERBATIM"
    assert CRAGAction.ATMA_VICHARA_REFLECTION.value == "ATMA_VICHARA_REFLECTION"
    assert CRAGAction.ABSTAIN.value == "ABSTAIN"
    assert CRAGDecision is CRAGAction


def test_crag_evaluation_result_properties():
    candidates = [{"score": 0.95, "verbatim_text": "Meditation dissolves the ego."}]
    res = evaluate_candidates(candidates, query="How to meditate?")

    assert res.action == CRAGAction.SERVE_VERBATIM
    assert res.decision == CRAGAction.SERVE_VERBATIM
    assert pytest.approx(res.confidence, rel=1e-4) == 0.95
    assert pytest.approx(res.confidence_score, rel=1e-4) == 0.95
    assert pytest.approx(res.top_score, rel=1e-4) == 0.95
    assert pytest.approx(res.dense_score, rel=1e-4) == 0.95
    assert res.tau_upper == 0.78
    assert res.tau_lower == 0.45
    assert res.reflection_prompt is None
    assert len(res.selected_candidates) == 1


def test_multi_candidate_top_to_bottom_margin():
    # 3 candidates: top-1 is 0.90, middle is 0.70, bottom is 0.40
    # margin = top - bottom = 0.90 - 0.40 = 0.50
    # confidence = 0.7 * 0.90 + 0.3 * 0.50 = 0.63 + 0.15 = 0.78
    candidates = [
        {"score": 0.90, "text": "Top hit"},
        {"score": 0.70, "text": "Middle hit"},
        {"score": 0.40, "text": "Bottom hit"},
    ]
    res = evaluate_candidates(candidates, query="Test query")
    assert pytest.approx(res.top_score, rel=1e-4) == 0.90
    assert pytest.approx(res.margin, rel=1e-4) == 0.50
    assert pytest.approx(res.confidence, rel=1e-4) == 0.78
    assert res.action == CRAGAction.SERVE_VERBATIM


def test_evaluate_candidates_custom_thresholds():
    candidates = [{"score": 0.60, "text": "Clip passage"}]
    # With tau_upper=0.55, score 0.60 qualifies for SERVE_VERBATIM
    res = evaluate_candidates(candidates, tau_upper=0.55, tau_lower=0.30)
    assert res.action == CRAGAction.SERVE_VERBATIM
    assert res.tau_upper == 0.55
    assert res.tau_lower == 0.30

    # With tau_upper=0.80, tau_lower=0.65, score 0.60 falls into ABSTAIN
    res_abstain = evaluate_candidates(candidates, tau_upper=0.80, tau_lower=0.65)
    assert res_abstain.action == CRAGAction.ABSTAIN
    assert res_abstain.selected_candidates == []


def test_exact_threshold_boundaries():
    evaluator = CRAGEvaluator(high_threshold=0.78, low_threshold=0.45)

    # 1. Exact boundary at 0.78 (single candidate => confidence = score)
    res_78 = evaluator.evaluate_scores(top_score=0.78)
    assert res_78.action == CRAGAction.SERVE_VERBATIM
    assert pytest.approx(res_78.confidence, rel=1e-4) == 0.78

    # 2. Just below upper threshold: 0.7799 -> ATMA_VICHARA_REFLECTION
    res_below_78 = evaluator.evaluate_scores(top_score=0.7799)
    assert res_below_78.action == CRAGAction.ATMA_VICHARA_REFLECTION
    assert res_below_78.reflection_prompt is not None

    # 3. Exact boundary at 0.45 -> ATMA_VICHARA_REFLECTION
    res_45 = evaluator.evaluate_scores(top_score=0.45)
    assert res_45.action == CRAGAction.ATMA_VICHARA_REFLECTION
    assert res_45.reflection_prompt is not None

    # 4. Just below lower threshold: 0.4499 -> ABSTAIN
    res_below_45 = evaluator.evaluate_scores(top_score=0.4499)
    assert res_below_45.action == CRAGAction.ABSTAIN
    assert res_below_45.reflection_prompt is None
    assert res_below_45.selected_candidates == []


def test_zero_and_negative_scores():
    evaluator = CRAGEvaluator()
    res_zero = evaluator.evaluate_scores(top_score=0.0)
    assert res_zero.action == CRAGAction.ABSTAIN
    assert res_zero.confidence == 0.0

    res_neg = evaluator.evaluate_scores(top_score=-0.2)
    assert res_neg.action == CRAGAction.ABSTAIN
    assert res_neg.confidence == 0.0

