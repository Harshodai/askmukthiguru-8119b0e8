"""CoVe enablement tests for tier3_complex / tier4_deep verification.

Proves that:
- CoVe (via container.llm_gateway.combined_verify / verify_answer) is invoked
  for tier3_complex and tier4_deep when those tiers are not in
  `rag_cove_disabled_for_tiers`.
- CoVe is skipped for fast/tier2_simple and standard tiers.
- Verification fails closed when no gateway is available.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import rag.nodes as nodes
from rag.states import GraphState


def _mock_state(query_tier: str, answer: str = "answer text") -> GraphState:
    return GraphState(
        question="What is the Beautiful State?",
        chat_history=[],
        request_id="test-req-cove",
        intent="FACTUAL",
        documents=[],
        reranked_docs=[],
        hyde_text=None,
        relevant_docs=[
            {
                "text": "Sri Preethaji teaches that the Beautiful State is a state of connection, a state of oneness, a state of peace, a state of love, a state of joy, and a state of compassion. It is not just an absence of suffering, but a positive presence of connection.",
                "source_url": "url1",
            }
        ],
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
        query_tier=query_tier,
    )


@pytest.fixture
def mock_gateway_services(monkeypatch):
    """Patch services with a mocked LLM gateway and LettuceDetect."""
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
    gateway.primary = MagicMock()
    gateway.primary.verify_answer = AsyncMock(
        return_value={
            "is_faithful": True,
            "passed": True,
            "confidence": 8.5,
            "details": "Gateway combined verification passed",
        }
    )
    nodes._llm_gateway = gateway

    mock_ld = MagicMock()
    mock_ld.score_faithfulness.return_value = {
        "is_faithful": True,
        "score": 0.9,
        "details": "Grounded.",
        "unsupported_sentences": [],
    }
    nodes._lettuce_detect = mock_ld

    return gateway, mock_ld


@pytest.mark.asyncio
@pytest.mark.parametrize("tier", ["tier3_complex", "tier4_deep"])
async def test_cove_called_for_high_tiers(mock_gateway_services, tier):
    gateway, _ = mock_gateway_services
    state = _mock_state(tier, answer="answer text " * 20)

    result = await nodes.verify_answer(state)

    gateway.primary.verify_answer.assert_awaited_once()
    assert result["is_faithful"] is True
    assert result["verification"]["passed"] is True
    assert result["confidence_score"] == 8.5
    assert result["faithfulness_score"] == 0.85


@pytest.mark.asyncio
@pytest.mark.parametrize("tier", ["fast", "tier2_simple"])
async def test_cove_skipped_for_simple_tiers(mock_gateway_services, tier):
    gateway, _ = mock_gateway_services
    state = _mock_state(tier)

    result = await nodes.verify_answer(state)

    gateway.primary.verify_answer.assert_not_called()
    assert result["is_faithful"] is True
    assert result["verification"]["passed"] is True
    assert result["verification"]["details"] == "Bypassed for simple query tier"


@pytest.mark.asyncio
async def test_cove_skipped_for_standard_tier(mock_gateway_services):
    gateway, _ = mock_gateway_services
    state = _mock_state("standard")

    result = await nodes.verify_answer(state)

    gateway.primary.verify_answer.assert_not_called()
    assert result["is_faithful"] is True
    assert result["verification"]["passed"] is True
    assert result["verification"]["details"] == "Bypassed for standard tier short answer"


@pytest.mark.asyncio
async def test_cove_disabled_via_settings(monkeypatch, mock_gateway_services):
    """When tier3_complex is added to the disabled list, gateway CoVe is skipped."""
    gateway, _ = mock_gateway_services
    monkeypatch.setattr(
        "rag.nodes.verification.settings.rag_cove_disabled_for_tiers",
        ["fast", "tier2_simple", "standard", "tier3_complex"],
    )

    state = _mock_state("tier3_complex", answer="answer text " * 20)
    result = await nodes.verify_answer(state)

    gateway.primary.verify_answer.assert_not_called()
    assert result["is_faithful"] is True
    assert result["verification"]["passed"] is True


@pytest.mark.asyncio
async def test_cove_falls_back_without_gateway(monkeypatch):
    """With no LLM gateway available, tier3_complex falls back to LettuceDetect."""
    from rag.nodes import _services

    monkeypatch.setattr(_services, "_llm_gateway", None)

    state = _mock_state("tier3_complex", answer="answer text " * 20)
    result = await nodes.verify_answer(state)

    assert result["is_faithful"] is True
    assert result["verification"]["passed"] is True


@pytest.mark.asyncio
async def test_cove_gateway_error_fails_closed(mock_gateway_services):
    gateway, _ = mock_gateway_services
    gateway.primary.verify_answer = AsyncMock(side_effect=RuntimeError("gateway down"))

    state = _mock_state("tier3_complex", answer="answer text " * 20)
    result = await nodes.verify_answer(state)

    assert result["is_faithful"] is False
    assert result["verification"]["passed"] is False
    assert "gateway down" in result["verification"]["details"]


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
