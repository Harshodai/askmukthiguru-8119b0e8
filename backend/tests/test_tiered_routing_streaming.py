"""
Unit tests for the tiered query routing and SSE streaming optimizations.
Verifies that simple queries bypass heavy nodes and that token streaming works.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import rag.nodes as nodes
from rag.resolve_followup import resolve_followup
from rag.states import GraphState


class MockEmbeddingService:
    def encode_single_full(self, text):
        return {"dense": [0.1] * 1024, "sparse": {}}

    def encode_batch(self, texts):
        return {"dense": [[0.1] * 1024 for _ in texts]}


@pytest.fixture
def mock_services():
    mock_ollama = AsyncMock()
    mock_embedder = MockEmbeddingService()
    mock_qdrant = MagicMock()
    mock_lightrag = MagicMock()

    nodes.init_services(
        ollama=mock_ollama, embedder=mock_embedder, qdrant=mock_qdrant, lightrag=mock_lightrag
    )

    mock_ld = MagicMock()
    nodes._lettuce_detect = mock_ld

    yield mock_ollama, mock_ld


@pytest.mark.asyncio
async def test_intent_router_tiered_classification(mock_services, monkeypatch):
    mock_ollama, _ = mock_services
    
    # Disable semantic router so it falls back to the mocked classify_intent_and_complexity
    from app.config import settings
    monkeypatch.setattr(settings, "use_semantic_router", False)
    
    async def mock_classify_intent_and_complexity(text, **kwargs):
        if "karma" in text:
            return {"intent": "FACTUAL", "complexity": "simple"}
        else:
            return {"intent": "FACTUAL", "complexity": "complex"}
    
    mock_ollama.classify_intent_and_complexity = mock_classify_intent_and_complexity

    # Test simple query classification
    state_simple = GraphState(
        question="What is karma?",
        chat_history=[],
        request_id="test-1",
        intent=None,
        query_tier=None,
    )

    res = await nodes.intent_router(state_simple)
    assert res["intent"] == "FACTUAL"
    assert res["query_tier"] == "tier2_simple"

    # Test complex query classification
    state_complex = GraphState(
        question="Compare Dvaita versus Advaita and explain how they differ",
        chat_history=[],
        request_id="test-2",
        intent=None,
        query_tier=None,
    )

    res_complex = await nodes.intent_router(state_complex)
    assert res_complex["intent"] == "FACTUAL"
    assert res_complex["query_tier"] == "tier3_complex"


@pytest.mark.asyncio
async def test_resolve_followup_bypass(mock_services):
    state = GraphState(
        question="What is meditation?",
        chat_history=[{"role": "user", "content": "hello"}],
        request_id="test-3",
        query_tier="tier2_simple",
    )
    # resolve_followup should immediately return {} without checking LLM when tier2_simple
    res = await resolve_followup(state)
    assert res == {}


@pytest.mark.asyncio
async def test_decompose_query_bypass(mock_services):
    state = GraphState(
        question="What is meditation?",
        chat_history=[],
        request_id="test-4",
        query_tier="tier2_simple",
    )
    res = await nodes.decompose_query(state)
    assert res["sub_queries"] == ["What is meditation?"]
    assert res["is_complex"] is False


@pytest.mark.asyncio
async def test_navigate_tree_bypass(mock_services):
    state = GraphState(
        question="What is meditation?",
        chat_history=[],
        request_id="test-5",
        query_tier="tier2_simple",
    )
    res = await nodes.navigate_knowledge_tree(state)
    assert res["selected_clusters"] == []


@pytest.mark.asyncio
async def test_hyde_bypass(mock_services):
    state = GraphState(
        question="What is meditation?",
        chat_history=[],
        request_id="test-6",
        query_tier="tier2_simple",
    )
    res = await nodes.generate_hyde(state)
    assert res["hyde_text"] is None


@pytest.mark.asyncio
async def test_grade_documents_bypass(mock_services):
    reranked = [{"text": "Meditation teaching", "source_url": "url1"}]
    state = GraphState(
        question="What is meditation?",
        chat_history=[],
        request_id="test-7",
        query_tier="tier2_simple",
        reranked_docs=reranked,
    )
    res = await nodes.grade_documents(state)
    assert res["relevant_docs"] == reranked


@pytest.mark.asyncio
async def test_check_sufficiency_bypass(mock_services):
    state = GraphState(
        question="What is meditation?",
        chat_history=[],
        request_id="test-8",
        query_tier="tier2_simple",
        relevant_docs=[{"text": "some teaching"}],
    )
    res = await nodes.check_context_sufficiency(state)
    assert "selected_clusters" not in res


@pytest.mark.asyncio
async def test_enrich_context_bypass(mock_services):
    docs = [{"text": "some teaching"}]
    state = GraphState(
        question="What is meditation?",
        chat_history=[],
        request_id="test-9",
        query_tier="tier2_simple",
        relevant_docs=docs,
    )
    res = await nodes.enrich_context(state)
    assert res["relevant_docs"] == docs


@pytest.mark.asyncio
async def test_quality_checks_bypass(mock_services):
    _, mock_ld = mock_services
    state = GraphState(
        question="What is meditation?",
        chat_history=[],
        request_id="test-10",
        query_tier="tier2_simple",
        answer="Meditation is calm.",
        relevant_docs=[{"text": "some teaching"}],
    )

    # reflect_on_answer bypass
    res_reflect = await nodes.reflect_on_answer(state)
    assert res_reflect["needs_correction"] is False
    assert res_reflect["reflection_feedback"] is None

    # verify_answer bypass
    res_verify = await nodes.verify_answer(state)
    assert res_verify["is_faithful"] is True
    assert res_verify["verification"]["passed"] is True
    assert res_verify["confidence_score"] == 10.0

    # check_contradiction bypass
    res_contradiction = await nodes.check_contradiction(state)
    assert "answer" not in res_contradiction

    # explain_retrieval bypass
    res_explain = await nodes.explain_retrieval(state)
    assert res_explain["citation_reasoning"] == {}


@pytest.mark.asyncio
async def test_generate_answer_streaming(mock_services):
    mock_ollama, _ = mock_services

    # Configure the generator mock for generate_stream
    async def mock_stream(*args, **kwargs):
        yield "M"
        yield "e"
        yield "d"
        yield "i"
        yield "t"
        yield "a"
        yield "t"
        yield "e"

    mock_ollama.generate_stream = mock_stream

    state = GraphState(
        question="What is meditation?",
        chat_history=[],
        request_id="test-11",
        query_tier="tier2_simple",
        relevant_docs=[{"text": "some teaching", "source_url": "url1"}],
        detected_language="en",
        ab_model="primary",
    )

    queue = asyncio.Queue()
    config = {"configurable": {"stream_queue": queue}}

    res = await nodes.generate_answer(state, config=config)
    assert res["answer"] == "Meditate\n\n*(Teachings referenced: meditation)*"

    # Verify queue contains the tokens
    tokens = []
    while not queue.empty():
        tokens.append(await queue.get())

    assert "".join(tokens) == "Meditate"


@pytest.mark.asyncio
async def test_context_compression_threshold(mock_services):
    mock_ollama, _ = mock_services
    mock_ollama.compress_context = AsyncMock(return_value="compressed text")
    mock_ollama.generate = AsyncMock(return_value="dummy response")
    mock_ollama.generate_stream = None  # Force synchronous fallback for simplicity

    from app.config import settings

    # Ensure it's enabled for the test
    settings.rag_use_context_compression = True
    settings.rag_context_compression_threshold = 100

    try:
        # 1. Total character length below threshold (should not compress)
        state_short = GraphState(
            question="What is meditation?",
            chat_history=[],
            request_id="test-short",
            query_tier="tier2_simple",
            relevant_docs=[{"text": "Short context.", "source_url": "url1"}],
            detected_language="en",
            ab_model="primary",
        )

        await nodes.generate_answer(state_short)
        mock_ollama.compress_context.assert_not_called()

        # 2. Total character length above threshold (should compress)
        state_long = GraphState(
            question="What is meditation?",
            chat_history=[],
            request_id="test-long",
            query_tier="tier2_simple",
            relevant_docs=[
                {
                    "text": "This is a very long context that will definitely exceed the threshold of 100 characters because it contains lots and lots of repetitive filler words to make it extremely long.",
                    "source_url": "url1",
                }
            ],
            detected_language="en",
            ab_model="primary",
        )

        mock_ollama.compress_context.reset_mock()
        await nodes.generate_answer(state_long)
        assert mock_ollama.compress_context.call_count == 1
        _, kwargs = mock_ollama.compress_context.call_args
        assert kwargs.get("question") == "What is meditation?"
        assert kwargs.get("text") == state_long["relevant_docs"][0]["text"]
    finally:
        # Reset settings defaults
        settings.rag_use_context_compression = False
        settings.rag_context_compression_threshold = 10000
