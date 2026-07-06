"""Adaptive-RAG confidence gate: high rerank confidence skips the LLM grading
and sufficiency calls for complex queries (crag_skip_confidence setting)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

import rag.nodes as nodes
from rag.nodes.reranking import check_context_sufficiency, grade_documents


def _doc(score: float, text: str = "teaching text") -> dict:
    return {"text": text, "rerank_score": score, "source_url": "https://youtu.be/x"}


@pytest.fixture
def mock_services():
    mock_ollama = AsyncMock()
    nodes.init_services(
        ollama=mock_ollama, embedder=MagicMock(), qdrant=MagicMock(), lightrag=MagicMock()
    )
    yield mock_ollama


@pytest.mark.asyncio
async def test_grading_skipped_when_rerank_confident(mock_services, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "crag_skip_confidence", 0.75)
    state = {
        "query_tier": "tier3_complex",
        "question": "What is the Beautiful State?",
        "reranked_docs": [_doc(0.9), _doc(0.85), _doc(0.8)],
    }

    result = await grade_documents(state)

    assert len(result["relevant_docs"]) == 3
    mock_services.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_grading_runs_when_confidence_low(mock_services, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "crag_skip_confidence", 0.75)
    mock_services.generate.return_value = "1: yes\n2: yes"
    state = {
        "query_tier": "tier3_complex",
        "question": "What is the Beautiful State?",
        "reranked_docs": [_doc(0.6), _doc(0.55), _doc(0.5)],
    }

    result = await grade_documents(state)

    # Bypass must NOT fire — the LLM grading path decides relevance.
    assert result.get("evaluation_trace", {}).get("grading_skipped_high_confidence") is not True


@pytest.mark.asyncio
async def test_sufficiency_skipped_when_rerank_confident(mock_services, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "crag_skip_confidence", 0.75)
    state = {
        "query_tier": "tier3_complex",
        "intent": "FACTUAL",
        "question": "What is the Beautiful State?",
        "relevant_docs": [_doc(0.9), _doc(0.85), _doc(0.8)],
    }

    result = await check_context_sufficiency(state)

    assert "selected_clusters" not in result  # no scope-widening triggered
    mock_services.generate.assert_not_awaited()
