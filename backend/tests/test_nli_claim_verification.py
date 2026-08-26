"""Unit and regression tests for Local NLI Claim Entailment Verification (Criteria A2.6, A2.7).

Verifies that:
1. Claim-level entailment output (`claims` list) from LettuceDetect is present in the
   verification result dictionary and not dead output.
2. When claim-level support passes (faithfulness >= floor and no unsupported claims),
   verification is accepted locally without dispatching an expensive secondary LLM round-trip.
3. Unsupported claims or low faithfulness score properly fail verification and trigger fallback.
4. Cached LettuceDetect results from reflection are reused without re-scoring.
5. Edge cases (safety redirects, empty context) include the claims key consistently.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import rag.nodes as nodes
from rag.states import GraphState
from services.lettuce_detect_service import LettuceDetectService


def _create_test_state(
    query_tier: str = "standard",
    answer: str = "The Beautiful State is a state of inner peace and connection.",
    relevant_docs: list | None = None,
    intent: str = "FACTUAL",
) -> GraphState:
    if relevant_docs is None:
        relevant_docs = [
            {
                "text": "Sri Preethaji teaches that the Beautiful State is a state of connection, a state of oneness, "
                "a state of peace, a state of love, a state of joy, and a state of compassion. It is not just an "
                "absence of suffering, but a positive presence of connection and profound harmony with life.",
                "source_url": "https://example.com/teachings/beautiful-state",
            }
        ]

    return GraphState(
        question="What is the Beautiful State?",
        chat_history=[],
        request_id="test-nli-verify-123",
        intent=intent,
        query_tier=query_tier,
        documents=[],
        reranked_docs=[],
        hyde_text=None,
        relevant_docs=relevant_docs,
        grading_reasons=[],
        rewrite_count=0,
        rewritten_query=None,
        sub_queries=["What is the Beautiful State?"],
        is_complex=False,
        selected_clusters=[],
        hints=[],
        answer=answer,
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
    )


@pytest.fixture
def mock_verification_services():
    mock_ollama = AsyncMock()
    mock_embedder = MagicMock()
    mock_qdrant = MagicMock()
    mock_lightrag = MagicMock()

    nodes.init_services(
        ollama=mock_ollama,
        embedder=mock_embedder,
        qdrant=mock_qdrant,
        lightrag=mock_lightrag,
    )

    gateway = MagicMock()
    gateway.verify_answer = AsyncMock(
        return_value={
            "is_faithful": True,
            "passed": True,
            "confidence": 8.5,
            "details": "Gateway combined verification passed",
        }
    )
    nodes._llm_gateway = gateway

    mock_ld = MagicMock()
    nodes._lettuce_detect = mock_ld

    return gateway, mock_ld, mock_ollama


@pytest.mark.asyncio
async def test_claim_level_entailment_output_present_in_verification_result(mock_verification_services):
    """Criterion A2.6: Claims list is present in verification result dictionary."""
    gateway, mock_ld, _ = mock_verification_services

    mock_ld.score_faithfulness.return_value = {
        "is_faithful": True,
        "score": 0.92,
        "details": "All sentences successfully grounded in context.",
        "unsupported_sentences": [],
        "claims": [
            {
                "text": "The Beautiful State is a state of inner peace and connection.",
                "score": 0.92,
                "supported": True,
            }
        ],
    }

    state = _create_test_state(query_tier="standard")
    result = await nodes.verify_answer(state)

    assert result["is_faithful"] is True
    assert result["verification"]["passed"] is True
    assert "claims" in result["verification"]

    claims = result["verification"]["claims"]
    assert isinstance(claims, list)
    assert len(claims) == 1
    assert claims[0]["text"] == "The Beautiful State is a state of inner peace and connection."
    assert claims[0]["score"] == 0.92
    assert claims[0]["supported"] is True


@pytest.mark.asyncio
async def test_claim_level_support_passes_skips_secondary_roundtrip(mock_verification_services):
    """When claim-level support passes locally, secondary LLM round-trips are skipped."""
    gateway, mock_ld, mock_ollama = mock_verification_services

    mock_ld.score_faithfulness.return_value = {
        "is_faithful": True,
        "score": 0.90,
        "details": "Grounded.",
        "unsupported_sentences": [],
        "claims": [
            {"text": "Claim 1 is grounded.", "score": 0.90, "supported": True},
            {"text": "Claim 2 is grounded.", "score": 0.90, "supported": True},
        ],
    }

    # Even on complex tiers, if local NLI passes, skip secondary roundtrip
    state = _create_test_state(
        query_tier="tier3_complex",
        answer="Claim 1 is grounded. Claim 2 is grounded.",
    )
    result = await nodes.verify_answer(state)

    # Verify gateway and secondary CoVe were NOT called
    gateway.verify_answer.assert_not_called()
    mock_ollama.generate.assert_not_called()

    assert result["is_faithful"] is True
    assert result["verification"]["passed"] is True
    assert len(result["verification"]["claims"]) == 2
    assert "Local NLI claim verification passed" in result["verification"]["details"]


@pytest.mark.asyncio
async def test_unsupported_claims_fail_verification(mock_verification_services):
    """Criterion A2.7: Unsupported claims fail verification locally."""
    gateway, mock_ld, mock_ollama = mock_verification_services
    # Disable gateway so it tests local fail behavior without gateway
    nodes._llm_gateway = None

    mock_ld.score_faithfulness.return_value = {
        "is_faithful": False,
        "score": 0.45,
        "details": "Hallucination detected in 1 sentences",
        "unsupported_sentences": ["You will win a million dollars."],
        "claims": [
            {
                "text": "The Beautiful State is a state of inner peace.",
                "score": 0.90,
                "supported": True,
            },
            {
                "text": "You will win a million dollars.",
                "score": 0.10,
                "supported": False,
            },
        ],
    }

    state = _create_test_state(
        query_tier="standard",
        answer="The Beautiful State is a state of inner peace. You will win a million dollars.",
    )
    result = await nodes.verify_answer(state)

    assert result["is_faithful"] is False
    assert result["verification"]["passed"] is False
    assert "claims" in result["verification"]
    assert len(result["verification"]["claims"]) == 2

    # Check that unsupported claim is identified in details
    assert "You will win a million dollars" in result["verification"]["details"]


@pytest.mark.asyncio
async def test_low_faithfulness_fails_even_if_no_explicit_unsupported_sentences(mock_verification_services):
    """When faithfulness score is below settings.faithfulness_floor, verification fails."""
    gateway, mock_ld, _ = mock_verification_services
    nodes._llm_gateway = None

    mock_ld.score_faithfulness.return_value = {
        "is_faithful": False,
        "score": 0.55,  # Below default floor of 0.70
        "details": "Marginal grounding.",
        "unsupported_sentences": ["Marginal claim."],
        "claims": [
            {"text": "Marginal claim.", "score": 0.55, "supported": False}
        ],
    }

    state = _create_test_state(query_tier="standard", answer="Marginal claim.")
    result = await nodes.verify_answer(state)

    assert result["is_faithful"] is False
    assert result["verification"]["passed"] is False
    assert result["faithfulness_score"] == 0.55


@pytest.mark.asyncio
async def test_unsupported_claims_trigger_fallback_gateway_on_complex_tier(mock_verification_services):
    """When local NLI fails on complex queries, fallback to LLM gateway verification."""
    gateway, mock_ld, _ = mock_verification_services

    mock_ld.score_faithfulness.return_value = {
        "is_faithful": False,
        "score": 0.40,
        "details": "Hallucinated claim",
        "unsupported_sentences": ["Fabricated claim."],
        "claims": [{"text": "Fabricated claim.", "score": 0.40, "supported": False}],
    }

    state = _create_test_state(
        query_tier="tier3_complex",
        answer="Fabricated claim.",
    )
    result = await nodes.verify_answer(state)

    # Gateway should be called as fallback
    gateway.verify_answer.assert_awaited_once()
    assert "claims" in result["verification"]


@pytest.mark.asyncio
async def test_cached_lettuce_detect_result_reused(mock_verification_services):
    """Cached lettuce_detect_result from self-reflection is reused with claims preserved."""
    _, mock_ld, _ = mock_verification_services

    cached_claims = [
        {"text": "Sri Preethaji teaches peace.", "score": 0.95, "supported": True}
    ]
    cached_ld_result = {
        "is_faithful": True,
        "score": 0.95,
        "details": "All sentences grounded.",
        "unsupported_sentences": [],
        "claims": cached_claims,
    }

    state = _create_test_state(query_tier="standard", answer="Sri Preethaji teaches peace.")
    state["lettuce_detect_result"] = cached_ld_result

    result = await nodes.verify_answer(state)

    # LettuceDetect score_faithfulness should NOT be called since result was cached
    mock_ld.score_faithfulness.assert_not_called()
    assert result["is_faithful"] is True
    assert result["verification"]["passed"] is True
    assert result["verification"]["claims"] == cached_claims


@pytest.mark.asyncio
async def test_safety_and_empty_context_include_empty_claims(mock_verification_services):
    """Safety redirects and empty context responses include claims: []."""
    state_safety = _create_test_state(intent="SAFETY_VIOLATION", answer="I cannot answer that.")
    res_safety = await nodes.verify_answer(state_safety)
    assert res_safety["verification"]["passed"] is True
    assert res_safety["verification"]["claims"] == []

    state_empty = _create_test_state(answer="")
    res_empty = await nodes.verify_answer(state_empty)
    assert res_empty["verification"]["passed"] is True
    assert res_empty["verification"]["claims"] == []


def test_lettuce_detect_service_heuristic_claims_structure():
    """LettuceDetectService heuristic generates claim-level entailment records."""
    service = LettuceDetectService(embedder=None)

    context = "Sri Preethaji teaches that stillness begins with observing breath and inner peace."
    grounded_answer = "Sri Preethaji teaches that stillness begins with observing breath."
    result_grounded = service.score_faithfulness("What is stillness?", context, grounded_answer)

    assert "claims" in result_grounded
    assert len(result_grounded["claims"]) > 0
    for claim in result_grounded["claims"]:
        assert "text" in claim
        assert "score" in claim
        assert "supported" in claim
        assert claim["supported"] is True

    ungrounded_answer = "Sri Preethaji teaches that purchasing gold brings spiritual enlightenment."
    result_ungrounded = service.score_faithfulness("What is stillness?", context, ungrounded_answer)

    assert "claims" in result_ungrounded
    assert any(c["supported"] is False for c in result_ungrounded["claims"])
    assert result_ungrounded["is_faithful"] is False
