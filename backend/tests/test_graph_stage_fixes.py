from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.stages import GraphStage
from app.pipeline.stages.context import PipelineContext
from services.nim_service import NimService


class _DirectCoalescer:
    async def get_or_run(self, key, callback):
        return await callback()

@pytest.mark.asyncio
async def test_graph_stage_distress_never_downgraded_to_fast():
    # Setup mock container
    container = MagicMock()
    
    # Mock fast, standard, deep graphs
    mock_fast_graph = AsyncMock()
    mock_fast_graph.nodes = {"handle_distress_check": {}, "handle_distress": {}}
    mock_fast_graph.ainvoke.return_value = {"final_answer": "distress answered", "citations": [], "intent": "DISTRESS"}
    
    mock_standard_graph = AsyncMock()
    mock_standard_graph.nodes = {"handle_distress_check": {}, "handle_distress": {}}
    mock_standard_graph.ainvoke.return_value = {"final_answer": "standard answered", "citations": [], "intent": "DISTRESS"}
    
    container.fast_graph = mock_fast_graph
    container.standard_graph = mock_standard_graph
    container.deep_graph = mock_standard_graph
    
    # Setup coordinator using real PipelineCoordinator with DirectCoalescer
    coordinator = PipelineCoordinator(container)
    coordinator.coalescer = _DirectCoalescer()
    
    # Setup PipelineContext
    ctx = PipelineContext(
        container=container,
        coordinator=coordinator,
        request=MagicMock(),
        user_msg="I feel very sad and in distress",
        preferred_lang="en",
        meditation_step=0,
        session_id="sess-1",
        user={"id": "user-1"},
        is_benchmark=False,
    )
    # Set pre-detected query tier and pre-populated state
    ctx.detected_query_tier = "fast"
    ctx.state = {
        "user_msg_en": "I feel very sad and in distress",
        "chat_history_en": [],
        "memory_context": "",
        "lang_detection": None,
        "query_tier": "tier2_simple",
        "intent": "DISTRESS",
    }
    
    # We mock classify_with_reason to return DISTRESS
    with patch("rag.nodes.on_device_intent.classify_with_reason") as mock_classify:
        mock_classify.return_value = ("DISTRESS", "sad user")
        
        # Execute GraphStage
        stage = GraphStage()
        await stage.run(ctx)
        
        # Since detected_intent is DISTRESS, it should have used the standard_graph instead of fast_graph
        assert mock_standard_graph.ainvoke.called
        assert not mock_fast_graph.ainvoke.called


@pytest.mark.asyncio
async def test_graph_stage_fast_graph_missing_nodes_fallback():
    # Setup mock container
    container = MagicMock()
    
    # Mock fast graph WITHOUT required distress nodes
    mock_fast_graph = AsyncMock()
    mock_fast_graph.nodes = {"retrieve_documents": {}, "generate_answer": {}}  # missing distress nodes!
    mock_fast_graph.ainvoke.return_value = {"final_answer": "fast answered", "citations": [], "intent": "FACTUAL"}
    
    mock_standard_graph = AsyncMock()
    mock_standard_graph.ainvoke.return_value = {"final_answer": "standard answered", "citations": [], "intent": "FACTUAL"}
    
    container.fast_graph = mock_fast_graph
    container.standard_graph = mock_standard_graph
    container.deep_graph = mock_standard_graph
    
    # Setup coordinator using real PipelineCoordinator with DirectCoalescer
    coordinator = PipelineCoordinator(container)
    coordinator.coalescer = _DirectCoalescer()
    
    ctx = PipelineContext(
        container=container,
        coordinator=coordinator,
        request=MagicMock(),
        user_msg="what is soul sync",
        preferred_lang="en",
        meditation_step=0,
        session_id="sess-1",
        user={"id": "user-1"},
        is_benchmark=False,
    )
    ctx.detected_query_tier = "fast"
    ctx.state = {
        "user_msg_en": "what is soul sync",
        "chat_history_en": [],
        "memory_context": "",
        "lang_detection": None,
        "query_tier": "tier2_simple",
        "intent": "FACTUAL",
    }
    
    with patch("rag.nodes.on_device_intent.classify_with_reason") as mock_classify:
        mock_classify.return_value = ("FACTUAL", "simple query")
        
        stage = GraphStage()
        await stage.run(ctx)
        
        # Since fast_graph was missing nodes, it should fall back to standard_graph
        assert mock_standard_graph.ainvoke.called
        assert not mock_fast_graph.ainvoke.called


@pytest.mark.asyncio
async def test_graph_stage_deep_pattern_not_force_fasted():
    """A CacheCheckStage 'deep' classification (regex-matched comparative
    query) must not be discarded when the on-device classifier separately
    guessed tier2_simple -- that discarding routed comparative queries like
    "difference between Soul Sync and Serene Mind" onto the fast graph,
    which skips grade_documents/verify_answer/extract_citations entirely.
    """
    container = MagicMock()

    mock_fast_graph = AsyncMock()
    mock_fast_graph.nodes = {"handle_distress_check": {}, "handle_distress": {}}
    mock_fast_graph.ainvoke.return_value = {"final_answer": "fast answered", "citations": [], "intent": "FACTUAL"}

    mock_deep_graph = AsyncMock()
    mock_deep_graph.ainvoke.return_value = {"final_answer": "deep answered", "citations": [], "intent": "FACTUAL"}

    container.fast_graph = mock_fast_graph
    container.standard_graph = mock_deep_graph
    container.deep_graph = mock_deep_graph

    coordinator = PipelineCoordinator(container)
    coordinator.coalescer = _DirectCoalescer()

    ctx = PipelineContext(
        container=container,
        coordinator=coordinator,
        request=MagicMock(),
        user_msg="difference between soul sync and serene mind breathing",
        preferred_lang="en",
        meditation_step=0,
        session_id="sess-1",
        user={"id": "user-1"},
        is_benchmark=False,
    )
    # CacheCheckStage's intent-blind classifier caught a HEURISTIC_DEEP_PATTERNS
    # match ("difference between") and resolved "deep".
    ctx.detected_query_tier = "deep"
    ctx.state = {
        "user_msg_en": "difference between soul sync and serene mind breathing",
        "chat_history_en": [],
        "memory_context": "",
        "lang_detection": None,
        "query_tier": None,
        "intent": None,
    }

    with patch("rag.nodes.on_device_intent.classify_with_reason") as mock_classify:
        # On-device classifier's coarser guess: FACTUAL -> tier2_simple.
        mock_classify.return_value = ("FACTUAL", "looks like a simple factual question")

        stage = GraphStage()
        await stage.run(ctx)

        assert mock_deep_graph.ainvoke.called
        assert not mock_fast_graph.ainvoke.called


@pytest.mark.asyncio
async def test_graph_stage_query_tier_synced_to_selected_graph():
    """When graph_variant resolves to standard/deep but the on-device
    classifier already stamped state['query_tier']='tier2_simple', every
    in-graph gate (grade_documents, verify_answer, retrieval depth) reads
    state['query_tier'] and would self-bypass real grading/verification on
    the stale tag. GraphStage must promote it to 'standard' so nodes inside
    the actually-selected graph behave consistently with graph_variant.
    """
    container = MagicMock()

    mock_fast_graph = AsyncMock()
    mock_fast_graph.nodes = {"handle_distress_check": {}, "handle_distress": {}}

    captured_state = {}

    async def _capture_invoke(state, config=None):
        captured_state.update(state)
        return {"final_answer": "deep answered", "citations": [], "intent": "FACTUAL"}

    mock_deep_graph = AsyncMock()
    mock_deep_graph.ainvoke.side_effect = _capture_invoke

    container.fast_graph = mock_fast_graph
    container.standard_graph = mock_deep_graph
    container.deep_graph = mock_deep_graph

    coordinator = PipelineCoordinator(container)
    coordinator.coalescer = _DirectCoalescer()

    ctx = PipelineContext(
        container=container,
        coordinator=coordinator,
        request=MagicMock(),
        user_msg="difference between soul sync and serene mind breathing",
        preferred_lang="en",
        meditation_step=0,
        session_id="sess-1",
        user={"id": "user-1"},
        is_benchmark=False,
    )
    ctx.detected_query_tier = "deep"
    ctx.state = {
        "user_msg_en": "difference between soul sync and serene mind breathing",
        "chat_history_en": [],
        "memory_context": "",
        "lang_detection": None,
        "query_tier": None,
        "intent": None,
    }

    with patch("rag.nodes.on_device_intent.classify_with_reason") as mock_classify:
        mock_classify.return_value = ("FACTUAL", "looks like a simple factual question")

        stage = GraphStage()
        await stage.run(ctx)

        assert captured_state.get("query_tier") == "standard"


@pytest.mark.asyncio
async def test_nim_service_fallback_ignores_model_param():
    # Instantiate NimService
    nim = NimService()
    
    # Mock _sarvam_fallback
    mock_sarvam = AsyncMock()
    nim._sarvam_fallback = mock_sarvam
    
    # We will trigger _fallback_to_sarvam
    # It should call _sarvam_fallback._call_api with model=settings.sarvam_cloud_model, NOT the NIM model
    await nim._fallback_to_sarvam(
        messages=[{"role": "user", "content": "hi"}],
        model="meta/llama-3.1-8b-instruct",  # incoming NIM model
        max_tokens=100,
        temperature=0.1,
        operation="generate",
    )
    
    mock_sarvam._call_api.assert_called_once()
    kwargs = mock_sarvam._call_api.call_args[1]
    assert kwargs["model"] == getattr(settings, "sarvam_cloud_model", "sarvam-30b")
    assert kwargs["model"] != "meta/llama-3.1-8b-instruct"
