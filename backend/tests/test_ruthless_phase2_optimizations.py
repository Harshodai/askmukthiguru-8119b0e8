"""Unit tests for Phase 2 Ruthless Remediation optimizations:
1. §7 & §9 Selective reranking bypass & CRAG high-confidence flag
2. §8 Context engineering evidence deduplication
3. §11 Fallback attribution in evaluation_trace
4. §13 Node latency attribution in format_final_answer
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from rag.nodes.reranking import rerank_documents, grade_documents
from rag.nodes.generation import context_engineer, format_final_answer
from app.config import settings


@pytest.mark.asyncio
async def test_rerank_bypass_high_confidence():
    """Verify that high-confidence retrieval skips cross-encoder for fast/simple tiers."""
    state = {
        "question": "What is the beautiful state?",
        "rewritten_query": None,
        "query_tier": "tier2_simple",
        "documents": [
            {
                "title": "Beautiful State",
                "source_url": "https://example.com/bs.md",
                "text": "A beautiful state is a state of connection and peace.",
                "score": 0.92,
            },
            {
                "title": "Inner Peace",
                "source_url": "https://example.com/peace.md",
                "text": "Peace comes from awareness.",
                "score": 0.70,
            },
        ],
    }

    res = await rerank_documents(state)
    assert len(res["reranked_docs"]) == 2
    assert res["evaluation_trace"].get("rerank_bypassed") is True
    # Highest scoring document should be at rank 0
    assert res["reranked_docs"][0]["rerank_score"] == 0.92


@pytest.mark.asyncio
async def test_grade_documents_high_confidence_sets_flag():
    """Verify grade_documents sets high_confidence_retrieval=True when all docs exceed skip_conf."""
    state = {
        "question": "What is the beautiful state?",
        "query_tier": "standard",
        "reranked_docs": [
            {
                "title": "Beautiful State",
                "source_url": "https://example.com/bs.md",
                "text": "A beautiful state is a state of connection and peace.",
                "rerank_score": 0.88,
            },
            {
                "title": "Peace and Calm",
                "source_url": "https://example.com/calm.md",
                "text": "Calmness is natural to consciousness.",
                "rerank_score": 0.82,
            },
        ],
    }

    res = await grade_documents(state)
    assert res.get("high_confidence_retrieval") is True
    assert res["evaluation_trace"].get("high_confidence_retrieval") is True
    assert res["evaluation_trace"].get("grading_skipped_high_confidence") is True


@pytest.mark.asyncio
async def test_context_engineer_deduplicates_near_identical_chunks():
    """Verify context_engineer prunes near-duplicate chunks before packing context."""
    state = {
        "question": "How to meditate in stillness?",
        "intent": "QUERY",
        "query_tier": "standard",
        "relevant_docs": [
            {
                "title": "Stillness Practice 1",
                "source_url": "https://example.com/stillness1.md",
                "text": "To meditate in stillness, sit quietly and observe your breathing without any effort or struggle.",
                "rerank_score": 0.85,
            },
            {
                "title": "Stillness Practice Duplicate",
                "source_url": "https://example.com/stillness2.md",
                # Almost identical text (same words, minor change)
                "text": "To meditate in stillness, sit quietly and observe your breathing without effort or struggle.",
                "rerank_score": 0.80,
            },
            {
                "title": "Separate Teaching",
                "source_url": "https://example.com/different.md",
                "text": "The mind creates suffering when it resists the reality of what is occurring in the present moment.",
                "rerank_score": 0.78,
            },
        ],
    }

    res = await context_engineer(state)
    # The duplicate should be pruned, leaving 2 unique chunks
    selected = res["selected_docs"]
    assert len(selected) == 2
    assert res["evaluation_trace"].get("context_chunks_deduplicated") == 1
    assert res["evaluation_trace"].get("context_chunks_selected") == 2


@pytest.mark.asyncio
async def test_format_final_answer_preserves_node_timings():
    """Verify format_final_answer propagates node_timings to evaluation_trace."""
    state = {
        "question": "What is love?",
        "answer": "Love is connection without division. [Source: Sacred Teachings | URL: https://example.com/love.md]",
        "citations": ["https://example.com/love.md"],
        "intent": "QUERY",
        "query_tier": "fast",
        "relevant_docs": [
            {
                "title": "Sacred Teachings",
                "source_url": "https://example.com/love.md",
                "text": "Love is connection without division.",
            }
        ],
        "is_faithful": True,
        "faithfulness_score": 0.95,
        "confidence_score": 9.0,
        "verification": {"passed": True, "method": "test"},
        "node_timings": {
            "retrieve_documents": 42.5,
            "rerank_documents": 12.1,
            "generate_answer": 310.4,
            "verify_answer": 25.0,
        },
    }

    res = await format_final_answer(state)
    eval_trace = res.get("evaluation_trace", {})
    assert "node_timings" in eval_trace
    assert eval_trace["node_timings"]["retrieve_documents"] == 42.5
    assert eval_trace["node_timings"]["generate_answer"] == 310.4


@pytest.mark.asyncio
async def test_generate_answer_captures_fallback_telemetry():
    """Verify generate_answer captures fallback metadata in evaluation_trace when gateway fails."""
    from rag.nodes.generation import generate_answer
    from services.gateways.anthropic_gateway import AnthropicGatewayError

    state = {
        "question": "What is peace?",
        "rewritten_query": None,
        "query_tier": "standard",
        "intent": "QUERY",
        "selected_docs": [
            {
                "title": "Inner Peace",
                "source_url": "https://example.com/peace.md",
                "text": "Peace is stillness in action.",
            }
        ],
        "relevant_docs": [
            {
                "title": "Inner Peace",
                "source_url": "https://example.com/peace.md",
                "text": "Peace is stillness in action.",
            }
        ],
        "chat_history": [],
        "detected_language": "en",
        "evaluation_trace": {},
    }

    mock_ollama = MagicMock()
    mock_ollama.generate = AsyncMock(return_value="Peace is stillness in action.")
    mock_ollama.provider_name = "mock_ollama"
    mock_ollama.model = "llama3"

    with patch("rag.nodes._services._ollama", mock_ollama), \
         patch("services.gateways.anthropic_gateway.AnthropicGateway.from_settings", side_effect=AnthropicGatewayError("Simulated provider outage")):
        res = await generate_answer(state)

    eval_trace = res.get("evaluation_trace", {})
    assert eval_trace.get("fallback_occurred") is True
    assert "anthropic" in eval_trace.get("fallback_reason", "")
    assert eval_trace.get("fallback_from_provider") == "anthropic"
