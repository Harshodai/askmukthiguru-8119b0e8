"""Fail-closed regression tests for guardrails, intent fallback, and retrieval empty-set paths.

Fail-closed behavior means uncertain, malformed, or adversarial inputs are
handled safely rather than allowed to propagate through the pipeline.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from guardrails import LightweightGuardrails
from rag.graph_strategies import route_after_grading
from rag.nodes import intent as intent_module
from rag.nodes import retrieve_documents
from rag.nodes.short_circuit import handle_fallback


# ── Guardrails fail-closed ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_guardrails_fail_closed_on_blocked_topic():
    """Medical-advice queries must be blocked before they reach the pipeline."""
    guardrails = LightweightGuardrails()
    result = await guardrails.check_input("How to cure diabetes naturally?")

    assert result["blocked"] is True
    assert "medical" in result["reason"].lower() or "disease" in result["reason"].lower()


@pytest.mark.asyncio
async def test_guardrails_fail_closed_on_oversized_input():
    """Inputs exceeding the configured length limit must be blocked."""
    guardrails = LightweightGuardrails()
    long_message = "a" * 2001

    result = await guardrails.check_input(long_message)

    assert result["blocked"] is True
    assert "Input too long" in result["reason"]


@pytest.mark.asyncio
async def test_guardrails_fail_closed_on_self_harm():
    """Crisis/self-harm signals must always route to a safe response."""
    guardrails = LightweightGuardrails()
    result = await guardrails.check_input("I want to end my life")

    assert result["blocked"] is True
    assert "self_harm" in result["reason"] or "serene_mind" in result.get("redirect_to", "")
    assert "crisis" in result["response"].lower() or "please reach out" in result["response"].lower()


# ── Intent fallback fail-closed ───────────────────────────────────────────


class _LowDistressSereneMind:
    """Serene Mind stub that reports no distress so the fallback defaults to FACTUAL."""

    def assess_distress(self, message, conversation_history=None):
        return SimpleNamespace(level=0, confidence=0.0, detected_signals=[])


@pytest.mark.asyncio
async def test_intent_router_exception_fallback_defaults_to_factual(monkeypatch):
    """If intent classification crashes, the router must fall back to a safe FACTUAL intent."""

    async def _crashing_impl(state, config=None):
        raise RuntimeError("intent classifier unavailable")

    monkeypatch.setattr(intent_module, "_intent_router_impl", _crashing_impl)
    monkeypatch.setattr(intent_module._services, "_serene_mind", _LowDistressSereneMind())

    state = {
        "question": "What is the Beautiful State?",
        "chat_history": [],
    }
    result = await intent_module.intent_router(state, config=None)

    assert result["intent"] == "FACTUAL"
    assert result["query_tier"] == "tier2_simple"
    assert result["evaluation_trace"].get("routing_reason") == "intent_fallback_with_distress_check"


@pytest.mark.asyncio
async def test_intent_router_exception_fallback_enables_web_search_for_temporal_query(monkeypatch):
    """A crashing classifier must still detect temporal queries and enable web search."""

    async def _crashing_impl(state, config=None):
        raise RuntimeError("intent classifier unavailable")

    monkeypatch.setattr(intent_module, "_intent_router_impl", _crashing_impl)
    monkeypatch.setattr(intent_module._services, "_serene_mind", _LowDistressSereneMind())

    state = {
        "question": "When is the next Ekam event this year?",
        "chat_history": [],
    }
    result = await intent_module.intent_router(state, config=None)

    assert result["intent"] == "FACTUAL"
    assert result["query_tier"] == "tier3_complex"
    assert result["needs_web_search"] is True


@pytest.mark.asyncio
async def test_intent_router_exception_fallback_routes_distress(monkeypatch):
    """If the classifier crashes and distress keywords are present, route to DISTRESS."""

    class _ModerateDistressSereneMind:
        def assess_distress(self, message, conversation_history=None):
            return SimpleNamespace(level=2, confidence=0.8, detected_signals=["hopeless"])

    async def _crashing_impl(state, config=None):
        raise RuntimeError("intent classifier unavailable")

    monkeypatch.setattr(intent_module, "_intent_router_impl", _crashing_impl)
    monkeypatch.setattr(intent_module._services, "_serene_mind", _ModerateDistressSereneMind())

    state = {
        "question": "I feel hopeless and cannot go on",
        "chat_history": [],
    }
    result = await intent_module.intent_router(state, config=None)

    assert result["intent"] == "DISTRESS"
    assert result["query_tier"] == "tier2_simple"


# ── Retrieval empty-set fail-closed ────────────────────────────────────────


def _make_settings_proxy(max_rewrites: int = 2):
    """Create a minimal settings object for routing decisions."""
    return SimpleNamespace(rag_max_rewrites=max_rewrites)


def test_route_after_grading_empty_docs_triggers_rewrite(monkeypatch):
    """Empty retrieval with remaining rewrite budget should try rephrasing the query."""
    monkeypatch.setattr(
        "rag.graph_strategies.settings",
        _make_settings_proxy(max_rewrites=2),
    )
    state = {
        "relevant_docs": [],
        "rewrite_count": 0,
        "intent": "FACTUAL",
    }

    assert route_after_grading(state) == "rewrite"


def test_route_after_grading_empty_docs_exhausted_triggers_fallback(monkeypatch):
    """Empty retrieval after exhausting rewrites must fall back to a safe answer."""
    monkeypatch.setattr(
        "rag.graph_strategies.settings",
        _make_settings_proxy(max_rewrites=2),
    )
    state = {
        "relevant_docs": [],
        "rewrite_count": 2,
        "intent": "FACTUAL",
    }

    assert route_after_grading(state) == "fallback"


def test_route_after_grading_empty_docs_distress_prioritizes_distress_handler(monkeypatch):
    """Distress intent should bypass the fallback handler and use the compassionate one."""
    monkeypatch.setattr(
        "rag.graph_strategies.settings",
        _make_settings_proxy(max_rewrites=2),
    )
    state = {
        "relevant_docs": [],
        "rewrite_count": 2,
        "intent": "DISTRESS",
    }

    assert route_after_grading(state) == "distress"


@pytest.mark.asyncio
async def test_handle_fallback_returns_safe_response():
    """The fallback node must return a safe, honest 'I don't have that teaching' message."""
    state = {"question": "Unknown doctrine"}
    result = await handle_fallback(state, config=None)

    assert "final_answer" in result
    assert "don't have" in result["final_answer"].lower()


@pytest.mark.asyncio
async def test_retrieve_documents_empty_results_is_safe(monkeypatch):
    """If Qdrant returns no documents, retrieve_documents must still return gracefully."""
    import rag.nodes as nodes

    mock_embedder = MagicMock()
    mock_embedder.encode_single_full.return_value = {
        "dense": [0.1] * 1024,
        "sparse": {"1": 0.5},
    }

    mock_qdrant = MagicMock()
    mock_qdrant.search.return_value = []

    mock_ollama = AsyncMock()
    mock_ollama._generate_fast = AsyncMock(return_value="")

    monkeypatch.setattr(nodes, "_ollama", mock_ollama)
    monkeypatch.setattr(nodes, "_embedder", mock_embedder)
    monkeypatch.setattr(nodes, "_qdrant", mock_qdrant)
    monkeypatch.setattr(nodes, "_lightrag", None)
    monkeypatch.setattr(nodes, "_semantic_cache", None)

    # Build a settings namespace that disables the semantic cache branch while
    # preserving the real configuration values needed by the retrieval node.
    current_settings = nodes.settings
    patched_settings = SimpleNamespace(
        **vars(current_settings), SEMANTIC_CACHE_ENABLED=False
    )
    monkeypatch.setattr(nodes, "settings", patched_settings)

    state = {
        "question": "What is an unknown doctrine?",
        "chat_history": [],
        "rewritten_query": None,
        "sub_queries": [],
        "selected_clusters": [],
        "hyde_text": None,
        "intent": "FACTUAL",
        "query_tier": "fast",
        "knowledge_tags": [],
    }

    result = await retrieve_documents(state, config=None)

    assert "error" not in result
    assert "documents" in result
    assert result["documents"] == []
    assert result["evaluation_trace"].get("retrieved_count") == 0
