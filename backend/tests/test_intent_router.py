"""Regression tests for the intent router cache-hit path."""

from __future__ import annotations

import time as _time
from types import SimpleNamespace

import pytest

from rag.nodes import intent as intent_module
from rag.states import GraphState


def _make_state(question: str) -> GraphState:
    return {
        "question": question,
        "chat_history": [],
        "meditation_step": 0,
        "intent": None,
        "query_tier": None,
        "confidence_tier": None,
        "documents": [],
        "reranked_docs": [],
        "relevant_docs": [],
        "grading_reasons": [],
        "rewrite_count": 0,
        "rewritten_query": None,
        "sub_queries": [],
        "is_complex": False,
        "sub_query": None,
        "sub_results": [],
        "selected_clusters": [],
        "hints": [],
        "answer": None,
        "citations": [],
        "is_faithful": None,
        "needs_correction": False,
        "reflection_feedback": None,
        "verification": None,
        "confidence_score": None,
        "input_blocked": False,
        "output_blocked": False,
        "block_reason": None,
        "meditation_response": None,
        "final_answer": None,
        "error": None,
        "context_layers": None,
        "citation_reasoning": {},
        "metrics": {},
        "user_id": None,
        "detected_language": None,
        "memory_context": None,
        "ab_model": None,
        "model_used": None,
        "model_provider": None,
        "route_decision": None,
        "low_confidence_retrieval": None,
        "needs_web_search": False,
        "web_search_results": [],
        "node_timings": {},
        "evaluation_trace": {},
        "token_budget_remaining": 0,
        "request_id": "test-request-id",
    }


class _FakeSereneMind:
    def assess_distress(self, message, conversation_history=None):
        return SimpleNamespace(level=0, confidence=0.0, detected_signals=[])


def _patch_for_cache(monkeypatch, intent_module):
    """Disable every short-circuit so the cache branch is reached."""
    import app.config as config_module
    import rag.nodes as nodes_module

    fake_settings = SimpleNamespace(use_semantic_router=False)
    monkeypatch.setattr(nodes_module, "settings", fake_settings)
    monkeypatch.setattr(config_module, "settings", fake_settings)
    monkeypatch.setattr(intent_module, "settings", fake_settings)
    monkeypatch.setattr(intent_module._services, "_serene_mind", _FakeSereneMind())

    import rag.intent_prerouter as prerouter

    monkeypatch.setattr(prerouter, "preroute_intent", lambda q: None)


@pytest.mark.asyncio
async def test_intent_router_cache_hit_returns_cached_values(monkeypatch):
    """Cache hit must short-circuit classification and return cached intent/tier."""
    question = "zqxw mnpo rtyf ghlk vbnm"
    cache_key = question.lower().strip()

    intent_module._intent_classification_cache[cache_key] = ("FACTUAL", "simple", _time.time())

    _patch_for_cache(monkeypatch, intent_module)

    state = _make_state(question)

    try:
        result = await intent_module.intent_router(state, config=None)
    finally:
        intent_module._intent_classification_cache.pop(cache_key, None)

    assert result["intent"] == "FACTUAL"
    assert result["query_tier"] == "tier2_simple"
    assert result["confidence_tier"] == "high"
    assert result["evaluation_trace"].get("routing_reason") == "cache_hit"


@pytest.mark.asyncio
async def test_intent_router_cache_hit_query_mapped_to_factual(monkeypatch):
    """Cached QUERY intents must be normalized to FACTUAL on retrieval."""
    question = "plmn kjhg fdsa qwerty zxcvb"
    cache_key = question.lower().strip()

    intent_module._intent_classification_cache[cache_key] = ("QUERY", "complex", _time.time())

    _patch_for_cache(monkeypatch, intent_module)

    state = _make_state(question)

    try:
        result = await intent_module.intent_router(state, config=None)
    finally:
        intent_module._intent_classification_cache.pop(cache_key, None)

    assert result["intent"] == "FACTUAL"
    assert result["query_tier"] == "tier3_complex"
    assert result["evaluation_trace"].get("routing_reason") == "cache_hit"


class _DistressModerate:
    level = 2  # DistressLevel.MODERATE
    confidence = 0.8
    detected_signals = ["hopeless"]


class _FakeSereneMindDistress:
    def assess_distress(self, message, conversation_history=None):
        return _DistressModerate()


@pytest.mark.asyncio
async def test_intent_router_exception_fallback_routes_distress(monkeypatch):
    """If the classifier crashes, the fallback checks distress keywords and routes DISTRESS."""

    async def _impl(state, config=None):
        raise RuntimeError("classifier crashed")

    monkeypatch.setattr(intent_module, "_intent_router_impl", _impl)
    monkeypatch.setattr(
        intent_module._services, "_serene_mind", _FakeSereneMindDistress()
    )

    state = _make_state("I feel hopeless and cannot go on")
    result = await intent_module.intent_router(state, config=None)

    assert result["intent"] == "DISTRESS"
    assert result["query_tier"] == "tier2_simple"
    assert result["evaluation_trace"].get("routing_reason") == "intent_fallback_with_distress_check"


def test_intent_module_imports_without_indentation_error():
    """The module must parse and import successfully (regression for prior IndentationError)."""
    import ast

    import rag.nodes.intent as intent_mod

    source = intent_mod.__loader__.get_source(intent_mod.__name__)
    ast.parse(source)


class TestHeuristicFollowup:
    """Tests for _is_followup_heuristic in intent.py."""

    def _detect(self, question: str, chat_history: list | None = None) -> bool:
        from rag.nodes.intent import _is_followup_heuristic
        return _is_followup_heuristic(question, chat_history or [])

    def test_followup_phrase_detected(self):
        """Multi-word follow-up phrases must be detected."""
        chat = [{"role": "user", "content": "What is karma?"},
                {"role": "assistant", "content": "Karma is action."}]
        assert self._detect("tell me more", chat)
        assert self._detect("what about that", chat)
        assert self._detect("explain more about this", chat)
        assert self._detect("can you elaborate on that", chat)
        assert self._detect("go deeper", chat)

    def test_referential_pronoun_short_query(self):
        """Short query with referential pronoun must be detected."""
        chat = [{"role": "user", "content": "What is the Beautiful State?"}]
        assert self._detect("tell me about it", chat)
        assert self._detect("what is that", chat)
        assert self._detect("explain this", chat)

    def test_standalone_topic_not_followup(self):
        """Fresh topic query without references must NOT be detected."""
        chat = [{"role": "user", "content": "What is karma?"}]
        assert not self._detect("What is the Beautiful State?", chat)
        assert not self._detect("How do I meditate?", chat)

    def test_no_history_not_followup(self):
        """No chat history → never a follow-up."""
        assert not self._detect("tell me more", [])
        assert not self._detect("what is that", [])
        assert not self._detect("hello", [])

    def test_empty_string_not_followup(self):
        """Empty query must not crash or be detected."""
        chat = [{"role": "user", "content": "hi"}]
        assert not self._detect("", chat)
        assert not self._detect("   ", chat)


@pytest.mark.asyncio
async def test_tier4_deep_cue_promotes_query_tier(monkeypatch):
    """Deep-cue questions must be promoted to tier4_deep before cheap paths fire."""
    from rag.nodes import intent as intent_module

    import app.config as config_module
    import rag.nodes as nodes_module

    fake_settings = SimpleNamespace(use_semantic_router=False)
    monkeypatch.setattr(nodes_module, "settings", fake_settings)
    monkeypatch.setattr(config_module, "settings", fake_settings)
    monkeypatch.setattr(intent_module, "settings", fake_settings)
    monkeypatch.setattr(intent_module._services, "_serene_mind", _FakeSereneMind())

    import rag.intent_prerouter as prerouter
    monkeypatch.setattr(prerouter, "preroute_intent", lambda q: None)

    state = _make_state(
        "Give a comprehensive doctrinal synthesis connecting the Beautiful State, karma, and moksha"
    )

    result = await intent_module.intent_router(state, config=None)

    assert result["query_tier"] == "tier4_deep"
    assert result["intent"] == "FACTUAL"
    assert result["evaluation_trace"].get("routing_reason") == "tier4_deep_cue"
