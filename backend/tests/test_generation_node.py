"""Tests for generation node budget capping and SarvamCloudService DI."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

import rag.nodes as nodes
from rag.nodes import _services
from rag.nodes.generation import _compute_context_budget, generate_answer
from rag.states import GraphState


class TestGenerationTokenBudget:
    """Validate structurally that the budget masking bug is fixed."""

    def test_max_500_removed(self):
        """Check that max(500, ...) was removed from generation.py."""
        from rag.nodes import generation
        source = inspect.getsource(generation)
        assert "max(500, allowed_knowledge_tokens)" not in source, "Old max(500, ...) pattern still present"

    def test_allowed_knowledge_tokens_clamped_to_zero(self):
        """allowed_knowledge_tokens must be clamped to at least 0."""
        from rag.nodes import generation
        source = inspect.getsource(generation)
        assert "max(0, max_budget - (sys_tokens + base_user_tokens + 250))" in source, "Budget clamped to zero not found"


class TestSarvamCloudDI:
    """Confirm SarvamCloudService is injected via DI, not a lazy node singleton."""

    def test_sarvam_cloud_injected_into_services(self):
        """_sarvam_cloud must be a module-level attribute."""
        assert hasattr(_services, "_sarvam_cloud"), "_sarvam_cloud not in _services"

    def test_no_module_level_lazy_singleton(self):
        """Ensure the module-level _sarvam_cloud_service global was removed."""
        from rag.nodes import generation
        assert "_sarvam_cloud_service" not in generation.__dict__, "Lazy singleton still present in generation"


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
async def test_generate_answer_short_circuits_on_empty_relevant_docs(mock_services):
    """Zero relevant_docs must return the honest content-gap message without calling the LLM.

    Regression test for the 2026-07-16 incident (handoff.md P3): calling the
    LLM with empty context surfaced a misleading generic "connection issue"
    fallback instead of the true cause (nothing was retrieved).
    """
    mock_ollama = mock_services

    state = GraphState(
        question="Who is Sri Preethaji?",
        relevant_docs=[],
        chat_history=[],
        detected_language="en",
        intent="FACTUAL",
        ab_model="primary",
    )

    result = await generate_answer(state)

    assert "couldn't find relevant teachings" in result["answer"]
    assert result["citations"] == []
    assert result["is_faithful"] is True
    assert result["verification"]["method"] == "no_context_short_circuit"
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
