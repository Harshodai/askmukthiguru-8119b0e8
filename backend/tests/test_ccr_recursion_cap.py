"""Tests for P1-AI-8 CCR recursion cap in generation.py."""

from __future__ import annotations

import pytest
from unittest.mock import patch

import rag.nodes as nodes
from rag.nodes.generation import generate_answer
from rag.prompts.system import FALLBACK_RESPONSE
from rag.states import GraphState


class _MockEmbedder:
    def encode_single_full(self, text):
        return {"dense": [0.1] * 384, "sparse": {}}


class _MockProvider:
    """Provider whose generate returns answers in sequence (one per call)."""

    def __init__(self, answer: str):
        self.answers = [answer]

    async def generate(self, *args, **kwargs):
        if not self.answers:
            return ""
        return self.answers.pop(0)

    async def generate_stream(self, *args, **kwargs):
        if False:  # pragma: no cover - make this an async generator
            yield ""

    async def classify_intent_and_complexity(self, *args, **kwargs):
        return {"intent": "FACTUAL", "complexity": "simple"}

    def select_model(self, *args, **kwargs):
        return "mock-model"


@pytest.fixture(autouse=True)
def _reset_services():
    nodes.init_services(
        ollama=_MockProvider("answer"),
        embedder=_MockEmbedder(),
        qdrant=object(),
        lightrag=None,
        semantic_cache=None,
        sarvam_cloud=None,
    )
    nodes._lettuce_detect = None


@pytest.mark.asyncio
async def test_first_ccr_retrieve_works():
    """First [RETRIEVE:] round is allowed and rebuilds context."""
    doc = {"text": "original uncompressed text", "source_url": "https://example.com/doc"}
    compressed_doc = {"text": "compressed", "source_url": "https://example.com/doc"}

    # Force the test through the legacy Ollama path so _MockProvider is invoked.
    provider = _MockProvider(
        "Some answer [RETRIEVE: https://example.com/doc]"
    )
    provider.answers.append(
        "original uncompressed text thanks to the retrieved document"
    )
    nodes.init_services(
        ollama=provider,
        embedder=_MockEmbedder(),
        qdrant=object(),
        lightrag=None,
        semantic_cache=None,
        sarvam_cloud=None,
    )

    from app.config import settings

    state = GraphState(
        question="What is the teaching?",
        relevant_docs=[compressed_doc],
        raw_documents=[doc],
        chat_history=[],
        detected_language="en",
        intent="FACTUAL",
        query_tier="tier2_simple",
        ab_model="primary",
    )

    with patch.object(settings, "llm_provider", "ollama"):
        with patch.object(settings, "rag_context_compression_enabled", True):
            with patch.object(settings, "ollama_cloud_only", False):
                result = await generate_answer(state)

    # The second generate call used the uncompressed doc.
    assert "original uncompressed text" in result["answer"].lower()


@pytest.mark.asyncio
async def test_second_ccr_retrieve_falls_back():
    """A second [RETRIEVE:] round after the first falls back to FALLBACK_RESPONSE."""
    doc = {"text": "original uncompressed text", "source_url": "https://example.com/doc"}
    compressed_doc = {"text": "compressed", "source_url": "https://example.com/doc"}

    provider = _MockProvider("Answer [RETRIEVE: https://example.com/doc]")
    nodes.init_services(
        ollama=provider,
        embedder=_MockEmbedder(),
        qdrant=object(),
        lightrag=None,
        semantic_cache=None,
        sarvam_cloud=None,
    )

    from app.config import settings

    state = GraphState(
        question="What is the teaching?",
        relevant_docs=[compressed_doc],
        raw_documents=[doc],
        chat_history=[],
        detected_language="en",
        intent="FACTUAL",
        query_tier="tier2_simple",
        ab_model="primary",
        ccr_attempted=True,
    )

    with patch.object(settings, "llm_provider", "ollama"):
        with patch.object(settings, "rag_context_compression_enabled", True):
            with patch.object(settings, "ollama_cloud_only", False):
                result = await generate_answer(state)

    assert result["answer"] == FALLBACK_RESPONSE
