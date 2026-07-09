"""Verify rerank order survives budget truncation (P0-4)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import rag.nodes as nodes
from rag.nodes.generation import generate_answer
from rag.states import GraphState


class _MockEmbeddingService:
    def encode_single_full(self, text):
        return {"dense": [0.1] * 384, "sparse": {}}


@pytest.fixture
def mock_services():
    mock_ollama = AsyncMock()
    mock_ollama.generate.return_value = "Answer."
    mock_ollama.generate_stream.return_value = _aiter_chunks(["Answer."])
    nodes.init_services(
        ollama=mock_ollama,
        embedder=_MockEmbeddingService(),
        qdrant=MagicMock(),
        lightrag=MagicMock(),
        semantic_cache=None,
        sarvam_cloud=None,
    )
    nodes._lettuce_detect = MagicMock()
    yield mock_ollama


def _aiter_chunks(chunks):
    async def _gen():
        for c in chunks:
            yield c
    return _gen()


@pytest.mark.asyncio
async def test_budget_truncation_preserves_rerank_order(mock_services, monkeypatch):
    """Docs must survive the budget loop in rerank (input) order, not alphabetical."""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "llm_provider", "ollama")
    monkeypatch.setattr(app_settings, "max_tokens_per_request", 60)

    monkeypatch.setattr(
        "rag.nodes.generation._compute_context_budget",
        lambda **kwargs: (kwargs["baseline_tokens"], 240),
    )
    monkeypatch.setattr(
        "rag.nodes.generation._generation_route",
        lambda state, context_chars: {"max_tokens": 100, "temperature": 0.7, "_route_metadata": {}},
    )

    captured: list[list[dict]] = []

    def _capture(docs):
        captured.append(list(docs))
        return []

    monkeypatch.setattr("rag.nodes.generation._grounded_citation_urls", _capture)

    long_text_a = "alpha " * 80
    long_text_b = "beta " * 80
    long_text_c = "charlie " * 80

    relevant_docs = [
        {"text": long_text_a, "source_url": "https://z.example/a", "title": "Zeta", "score": 0.99},
        {"text": long_text_b, "source_url": "https://a.example/b", "title": "Alpha", "score": 0.95},
        {"text": long_text_c, "source_url": "https://m.example/c", "title": "Mid", "score": 0.50},
    ]

    state = GraphState(
        question="What is meditation?",
        relevant_docs=relevant_docs,
        chat_history=[],
        detected_language="en",
        intent="FACTUAL",
        ab_model="primary",
    )

    await generate_answer(state)

    assert captured, "_grounded_citation_urls was never called; budget loop may have been bypassed"
    surviving = captured[0]
    titles = [d.get("title") for d in surviving]
    assert titles[0] == "Zeta", f"rerank order not preserved; first surviving doc was {titles[0]}"
    assert "Mid" not in titles, "lowest-rerank doc should have been truncated; budget too large"
    assert titles == ["Zeta", "Alpha"], f"surviving docs not in rerank order: {titles}"

