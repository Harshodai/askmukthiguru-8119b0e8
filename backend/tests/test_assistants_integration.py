"""Tests for Custom Assistants & Notes backend integration.

Covers:
- Backward-compatible ``assistant`` block on chat requests
- Assistant persona override in prompt assembly
- Knowledge tag filtering + hard ``sky`` exclusion in Qdrant
- ``assistant_slug`` propagation to telemetry
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas import AssistantContext, ChatRequest
from app.telemetry_sink import SupabaseTelemetrySink
from rag.nodes.generation import context_engineer, generate_answer
from services.qdrant.searcher import QdrantSearcher
from services.qdrant_service import _build_tag_conditions

# ---------------------------------------------------------------------------
# Contract / backward compatibility
# ---------------------------------------------------------------------------

def test_chat_request_without_assistant_is_backward_compatible():
    """Existing clients that omit the assistant block must still parse."""
    req = ChatRequest(messages=[{"role": "user", "content": "Hello"}], user_message="Hello")
    assert req.assistant is None
    assert req.user_message == "Hello"


def test_chat_request_with_assistant_parses():
    """The optional assistant block is additive and preserves other fields."""
    req = ChatRequest(
        messages=[{"role": "user", "content": "Tell me about breath awareness"}],
        user_message="Tell me about breath awareness",
        assistant=AssistantContext(
            slug="breath-guide",
            system_prompt="You are a breath-work assistant.",
            knowledge_tags=["breath", "meditation"],
        ),
    )
    assert req.assistant.slug == "breath-guide"
    assert req.assistant.system_prompt == "You are a breath-work assistant."
    assert req.assistant.knowledge_tags == ["breath", "meditation"]


# ---------------------------------------------------------------------------
# Tag filtering
# ---------------------------------------------------------------------------

class TestTagConditions:
    """Unit tests for ``_build_tag_conditions``."""

    def test_sky_excluded_by_default(self):
        must, must_not = _build_tag_conditions([])
        assert not must
        assert any(
            fc.key == "tags" and fc.match.value == "sky" for fc in must_not
        )

    def test_sky_excluded_when_other_tags_requested(self):
        must, must_not = _build_tag_conditions(["love", "meditation"])
        assert any(fc.key == "tags" for fc in must)
        assert any(
            fc.key == "tags" and fc.match.value == "sky" for fc in must_not
        )

    def test_sky_allowed_when_explicitly_requested(self):
        must, must_not = _build_tag_conditions(["Sky"])
        assert any(
            fc.key == "tags" and "sky" in fc.match.any for fc in must
        )
        assert not any(
            fc.key == "tags" and fc.match.value == "sky" for fc in must_not
        )


class TestQdrantSearchFiltering:
    """Hybrid-search prefetches must all honor assistant tag filters."""

    @pytest.fixture
    def searcher(self):
        client = MagicMock()
        client.query_points.return_value = MagicMock(points=[])
        return QdrantSearcher(client, "test_collection")

    @staticmethod
    def _filter_predicates(filter_obj):
        """Flatten a Qdrant Filter into must/must_not/should key/value tuples."""
        out = {"must": [], "must_not": [], "should": []}
        for attr, key in [("must", "must"), ("must_not", "must_not"), ("should", "should")]:
            for cond in getattr(filter_obj, attr, []) or []:
                match = cond.match
                if hasattr(match, "value"):
                    out[key].append((cond.key, match.value))
                elif hasattr(match, "any"):
                    out[key].append((cond.key, tuple(match.any)))
        return out

    def test_hybrid_prefetches_include_tag_filters(self, searcher):
        searcher.search(
            query_vector=[0.1] * 384,
            limit=10,
            sparse_vector={"1": 0.5},
            knowledge_tags=["love"],
            query="what is love",
        )

        call = searcher._client.query_points.call_args
        prefetches = call.kwargs["prefetch"]

        for prefetch in prefetches:
            predicates = self._filter_predicates(prefetch.filter)
            assert ("tags", ("love",)) in predicates["must"], "requested tag must be required"
            assert ("tags", "sky") in predicates["must_not"], "sky must be excluded"

    def test_hybrid_prefetches_allow_sky_when_opted_in(self, searcher):
        searcher.search(
            query_vector=[0.1] * 384,
            limit=10,
            sparse_vector={"1": 0.5},
            knowledge_tags=["sky"],
            query="sky teachings",
        )

        call = searcher._client.query_points.call_args
        prefetches = call.kwargs["prefetch"]

        for prefetch in prefetches:
            predicates = self._filter_predicates(prefetch.filter)
            assert ("tags", ("sky",)) in predicates["must"]
            assert ("tags", "sky") not in predicates["must_not"]

    def test_dense_fallback_uses_tag_filter(self, searcher):
        """When no sparse vector is provided, dense-only search still filters."""
        searcher.search(
            query_vector=[0.1] * 384,
            limit=10,
            knowledge_tags=["meditation"],
        )

        call = searcher._client.query_points.call_args
        assert "query_filter" in call.kwargs
        predicates = self._filter_predicates(call.kwargs["query_filter"])
        assert ("tags", ("meditation",)) in predicates["must"]
        assert ("tags", "sky") in predicates["must_not"]

    def test_empty_knowledge_tags_exclude_sky(self, searcher):
        searcher.search(
            query_vector=[0.1] * 384,
            limit=10,
            sparse_vector={"1": 0.5},
            knowledge_tags=[],
            query="hello",
        )
        call = searcher._client.query_points.call_args
        for prefetch in call.kwargs["prefetch"]:
            predicates = self._filter_predicates(prefetch.filter)
            assert ("tags", "sky") in predicates["must_not"]
            assert not any(key == "tags" for key, _ in predicates["must"])

    def test_general_knowledge_tags_exclude_sky(self, searcher):
        searcher.search(
            query_vector=[0.1] * 384,
            limit=10,
            sparse_vector={"1": 0.5},
            knowledge_tags=["general"],
            query="what is love",
        )
        call = searcher._client.query_points.call_args
        for prefetch in call.kwargs["prefetch"]:
            predicates = self._filter_predicates(prefetch.filter)
            assert ("tags", ("general",)) in predicates["must"]
            assert ("tags", "sky") in predicates["must_not"]


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_engineer_uses_assistant_system_prompt():
    """A custom assistant prompt replaces the default persona layer."""
    state = {
        "question": "What is the Beautiful State?",
        "intent": "FACTUAL",
        "relevant_docs": [],
        "assistant_system_prompt": "You are a focused breath-work assistant.",
    }
    result = await context_engineer(state)
    assert "focused breath-work assistant" in result["context_layers"]["persona"]


@pytest.fixture
def mock_services():
    """Inject minimal mock services for generate_answer tests."""
    import rag.nodes as nodes
    mock_ollama = AsyncMock()
    mock_ollama.generate.return_value = "mock answer"

    class _MockEmbedder:
        def encode_single_full(self, text):
            return {"dense": [0.1] * 384, "sparse": {}}

    nodes.init_services(
        ollama=mock_ollama,
        embedder=_MockEmbedder(),
        qdrant=MagicMock(),
        lightrag=MagicMock(),
        semantic_cache=None,
        sarvam_cloud=None,
    )
    nodes._lettuce_detect = MagicMock()
    yield mock_ollama


@pytest.mark.asyncio
async def test_generate_answer_fallback_uses_assistant_prompt(mock_services, monkeypatch):
    """When no context layers exist, a custom assistant prompt still drives identity."""
    monkeypatch.setattr(
        "rag.nodes.generation._generation_route",
        lambda state, context_chars: {"max_tokens": 100, "temperature": 0.7, "_route_metadata": {}},
    )

    from services.gateways.anthropic_gateway import AnthropicGatewayError

    def _raise_from_settings(cls):
        raise AnthropicGatewayError("disabled in tests")

    monkeypatch.setattr(
        "services.gateways.anthropic_gateway.AnthropicGateway.from_settings",
        classmethod(_raise_from_settings),
    )

    state = {
        "question": "How do I meditate?",
        "rewritten_query": None,
        "relevant_docs": [],
        "chat_history": [],
        "detected_language": "en",
        "intent": "FACTUAL",
        "query_tier": "standard",
        "ab_model": "primary",
        "assistant_system_prompt": "You are a concise meditation assistant.",
    }

    await generate_answer(state)

    call = mock_services.generate.await_args
    system_prompt = call.kwargs["system_prompt"]
    assert "concise meditation assistant" in system_prompt
    # Safety layer should still be present
    assert "ONLY on the provided context" in system_prompt or "Cite sources" in system_prompt


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telemetry_includes_assistant_slug(monkeypatch):
    """``log_query_trace`` writes ``assistant_slug`` into the chat_queries row."""
    sink = SupabaseTelemetrySink.__new__(SupabaseTelemetrySink)
    sink.redis = None

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.upsert.return_value.execute = MagicMock()
    sink.client = mock_client

    await sink.log_query_trace(
        query_id="q-1",
        session_id="s-1",
        user_id="u-1",
        query_text="hello",
        model="sarvam-30b",
        latency_ms=100,
        status="success",
        created_at="2026-06-23T00:00:00Z",
        assistant_slug="health-assistant",
    )

    # chat_queries is upserted (idempotent — see the "duplicate chat queries"
    # fix); it's the last upsert on the shared mock_table.
    upserted = mock_table.upsert.call_args[0][0]
    assert upserted["assistant_slug"] == "health-assistant"


@pytest.mark.asyncio
async def test_telemetry_stream_includes_assistant_slug():
    sink = SupabaseTelemetrySink.__new__(SupabaseTelemetrySink)
    sink.client = None
    sink.redis = AsyncMock()

    await sink.log_query_trace(
        query_id="q-2",
        session_id="s-2",
        user_id="u-2",
        query_text="hello",
        model="sarvam-30b",
        latency_ms=100,
        status="success",
        created_at="2026-06-23T00:00:00Z",
        assistant_slug="stream-assistant",
    )

    serialized_payload = sink.redis.xadd.call_args.args[1]["payload"]
    payload = json.loads(serialized_payload)
    assert payload["assistant_slug"] == "stream-assistant"
