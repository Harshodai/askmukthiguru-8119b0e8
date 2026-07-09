"""Regression test for the cross-contaminating system-prompt cache (P0-1).

The cache keyed on `session_id:assistant_slug:detected_language` but
`session_id` was never injected into the LangGraph config, so all
English/default-assistant traffic collapsed to the same key. Since the
cached system prompt EMBEDS the retrieved context, a cache hit served a
later query an earlier query's teachings. The cache has been deleted; this
test proves two sequential calls on the SAME default config each see their
own retrieved context in the prompt sent to the LLM.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import rag.nodes as nodes
from rag.nodes.generation import generate_answer
from rag.states import GraphState


class MockEmbeddingService:
    def encode_single_full(self, text):
        return {"dense": [0.1] * 384, "sparse": {}}


@pytest.fixture
def mock_services():
    mock_ollama = AsyncMock()
    mock_ollama.generate.return_value = "answer"
    mock_ollama.generate_stream.return_value = _aiter_chunks(["answer"])
    nodes.init_services(
        ollama=mock_ollama,
        embedder=MockEmbeddingService(),
        qdrant=MagicMock(),
        lightrag=MagicMock(),
        semantic_cache=None,
        sarvam_cloud=None,
    )
    nodes._lettuce_detect = MagicMock()
    return mock_ollama


def _aiter_chunks(chunks):
    async def _gen():
        for c in chunks:
            yield c
    return _gen()


def _make_state(doc_text: str, title: str) -> GraphState:
    return GraphState(
        question="What is awakening?",
        relevant_docs=[{"text": doc_text, "title": title, "source_url": title}],
        chat_history=[],
        detected_language="en",
        intent="FACTUAL",
        ab_model="primary",
    )


@pytest.mark.asyncio
async def test_sequential_calls_do_not_cross_contaminate_context(mock_services, monkeypatch):
    """Two calls on the same default config must each send their own context."""
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "llm_provider", "ollama")
    monkeypatch.setattr(app_settings, "use_dspy", False)
    monkeypatch.setattr(
        "rag.nodes.generation._generation_route",
        lambda state, context_chars: {"max_tokens": 100, "temperature": 0.7, "_route_metadata": {}},
    )

    from services.gateways.anthropic_gateway import AnthropicGatewayError

    def _raise_from_settings(cls):
        raise AnthropicGatewayError("disabled in test")
    monkeypatch.setattr(
        "services.gateways.anthropic_gateway.AnthropicGateway.from_settings",
        classmethod(_raise_from_settings),
    )

    first_context = "UNIQUE_FIRST_TEACHING_MARKER_AAA"
    second_context = "UNIQUE_SECOND_TEACHING_MARKER_BBB"

    await generate_answer(_make_state(first_context, "doc-alpha"))
    await generate_answer(_make_state(second_context, "doc-beta"))

    first_call_kwargs = mock_services.generate.call_args_list[0].kwargs
    second_call_kwargs = mock_services.generate.call_args_list[1].kwargs

    first_prompt = first_call_kwargs["system_prompt"]
    second_prompt = second_call_kwargs["system_prompt"]

    assert first_context in first_prompt
    assert second_context not in first_prompt

    assert second_context in second_prompt
    assert first_context not in second_prompt
