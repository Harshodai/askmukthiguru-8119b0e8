"""
Unit tests for generation node reliability fixes (Unit 7).

- Semantic-cache write failures are logged, not swallowed.
- SarvamCloudService is used via dependency injection.
- AnthropicGateway config errors fall back to legacy LLM.
- Token budget helper clamps small budgets without overflow.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

import rag.nodes as nodes
from rag.nodes.generation import _compute_context_budget, format_final_answer, generate_answer
from rag.states import GraphState


class MockEmbeddingService:
    def encode_single_full(self, text):
        return {"dense": [0.1] * 384, "sparse": {}}


@pytest.fixture
def mock_services():
    mock_ollama = AsyncMock()
    mock_ollama.generate.return_value = "Ollama answer"
    mock_ollama.generate_stream.return_value = _aiter_chunks(["Ollama ", "answer"])
    mock_embedder = MockEmbeddingService()
    mock_qdrant = MagicMock()

    nodes.init_services(
        ollama=mock_ollama,
        embedder=mock_embedder,
        qdrant=mock_qdrant,
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
async def test_format_final_answer_logs_cache_write_error(mock_services, monkeypatch, caplog):
    """Semantic-cache write failures must be logged with full traceback."""
    cache = MagicMock()
    cache.put.side_effect = RuntimeError("redis down")
    monkeypatch.setattr(nodes, "_semantic_cache", cache)

    state = GraphState(
        question="What is the Beautiful State?",
        answer="The Beautiful State is connection.",
        citations=["https://example.com"],
        is_faithful=True,
        verification={"passed": True},
        confidence_score=8.0,
        intent="QUERY",
    )

    with caplog.at_level("ERROR", logger="rag.nodes.generation"):
        result = await format_final_answer(state)

    assert result["final_answer"] == "The Beautiful State is connection."
    assert "Semantic cache write failed" in caplog.text
    assert "redis down" in caplog.text


@pytest.mark.asyncio
async def test_generate_answer_uses_injected_sarvam_cloud(mock_services, monkeypatch):
    """When provider is sarvam_cloud, use the injected service instead of a new singleton."""
    mock_ollama = mock_services

    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "llm_provider", "sarvam_cloud")

    mock_sarvam = AsyncMock()
    mock_sarvam.generate.return_value = "Sarvam answer"
    mock_sarvam.generate_stream.return_value = _aiter_chunks(["Sarvam ", "answer"])
    monkeypatch.setattr(nodes, "_sarvam_cloud", mock_sarvam)

    monkeypatch.setattr(
        "rag.nodes.generation._generation_route",
        lambda state, context_chars: {"max_tokens": 100, "temperature": 0.7, "_route_metadata": {}},
    )

    state = GraphState(
        question="What is meditation?",
        relevant_docs=[{"text": "Meditation is calm awareness.", "source_url": "url1"}],
        chat_history=[],
        detected_language="en",
        intent="FACTUAL",
        ab_model="primary",
    )

    result = await generate_answer(state)

    assert result["answer"] == "Sarvam answer"
    mock_sarvam.generate.assert_awaited_once()
    mock_ollama.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_answer_falls_back_on_anthropic_config_error(mock_services, monkeypatch):
    """AnthropicGateway.from_settings errors must not crash the node."""
    mock_ollama = mock_services

    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "llm_provider", "ollama")

    from services.gateways.anthropic_gateway import AnthropicGatewayError

    def _raise_from_settings(cls):
        raise AnthropicGatewayError("bad config")

    monkeypatch.setattr(
        "services.gateways.anthropic_gateway.AnthropicGateway.from_settings",
        classmethod(_raise_from_settings),
    )

    monkeypatch.setattr(
        "rag.nodes.generation._generation_route",
        lambda state, context_chars: {"max_tokens": 100, "temperature": 0.7, "_route_metadata": {}},
    )

    state = GraphState(
        question="What is meditation?",
        relevant_docs=[{"text": "Meditation is calm awareness.", "source_url": "url1"}],
        chat_history=[],
        detected_language="en",
        intent="FACTUAL",
        ab_model="primary",
    )

    result = await generate_answer(state)

    assert "Ollama answer" in result["answer"]
    mock_ollama.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_answer_falls_back_when_sarvam_not_injected(mock_services, monkeypatch):
    """Provider sarvam_cloud without an injected service falls back to Ollama."""
    mock_ollama = mock_services

    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "llm_provider", "sarvam_cloud")
    monkeypatch.setattr(nodes, "_sarvam_cloud", None)

    monkeypatch.setattr(
        "rag.nodes.generation._generation_route",
        lambda state, context_chars: {"max_tokens": 100, "temperature": 0.7, "_route_metadata": {}},
    )

    state = GraphState(
        question="What is meditation?",
        relevant_docs=[{"text": "Meditation is calm awareness.", "source_url": "url1"}],
        chat_history=[],
        detected_language="en",
        intent="FACTUAL",
        ab_model="primary",
    )

    result = await generate_answer(state)

    assert "Ollama answer" in result["answer"]
    mock_ollama.generate.assert_awaited_once()


def test_compute_context_budget_clamps_small_budgets():
    """Small max_budget must not be masked by a max(..., ...) floor."""
    baseline, context = _compute_context_budget(
        max_budget=100,
        baseline_tokens=1500,
        history_str="",
        memory_context="",
    )
    assert baseline == 0
    assert context == 100


def test_compute_context_budget_enforces_ceiling():
    """Large baseline should not steal the whole budget from context."""
    baseline, context = _compute_context_budget(
        max_budget=2000,
        baseline_tokens=3000,
        history_str="",
        memory_context="",
    )
    assert baseline + context <= 2000
    assert context == 200


def test_compute_context_budget_keeps_history_and_memory_margin():
    """History and memory increase baseline but remain within budget."""
    baseline, context = _compute_context_budget(
        max_budget=2000,
        baseline_tokens=1500,
        history_str=" ".join(["word"] * 100),
        memory_context=" ".join(["memory"] * 50),
    )
    assert baseline > 1500
    assert baseline + context <= 2000
    assert context >= 200
