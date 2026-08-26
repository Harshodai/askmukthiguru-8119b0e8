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
    mock_fast_graph.ainvoke.return_value = {
        "final_answer": "distress answered",
        "citations": [],
        "intent": "DISTRESS",
    }

    mock_standard_graph = AsyncMock()
    mock_standard_graph.nodes = {"handle_distress_check": {}, "handle_distress": {}}
    mock_standard_graph.ainvoke.return_value = {
        "final_answer": "standard answered",
        "citations": [],
        "intent": "DISTRESS",
    }

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
    mock_fast_graph.nodes = {
        "retrieve_documents": {},
        "generate_answer": {},
    }  # missing distress nodes!
    mock_fast_graph.ainvoke.return_value = {
        "final_answer": "fast answered",
        "citations": [],
        "intent": "FACTUAL",
    }

    mock_standard_graph = AsyncMock()
    mock_standard_graph.ainvoke.return_value = {
        "final_answer": "standard answered",
        "citations": [],
        "intent": "FACTUAL",
    }

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
    mock_fast_graph.ainvoke.return_value = {
        "final_answer": "fast answered",
        "citations": [],
        "intent": "FACTUAL",
    }

    mock_standard_graph = AsyncMock()
    mock_standard_graph.ainvoke.return_value = {
        "final_answer": "standard answered",
        "citations": [],
        "intent": "FACTUAL",
    }

    mock_deep_graph = AsyncMock()
    mock_deep_graph.ainvoke.return_value = {
        "final_answer": "deep answered",
        "citations": [],
        "intent": "FACTUAL",
    }

    container.fast_graph = mock_fast_graph
    container.standard_graph = mock_standard_graph
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
        assert not mock_standard_graph.ainvoke.called


@pytest.mark.asyncio
async def test_graph_stage_query_tier_synced_to_selected_graph():
    """When graph_variant resolves to deep but the on-device classifier
    already stamped state['query_tier']='tier2_simple', every in-graph gate
    (grade_documents, verify_answer, retrieval depth) reads
    state['query_tier'] and would self-bypass real grading/verification on
    the stale tag. GraphStage must promote it to a tier consistent with the
    actually-selected graph -- 'tier4_deep' for graph_variant=='deep', so
    tier4_deep-gated logic (deep_contradiction_gate, route_after_verification)
    isn't silently downgraded out of its own extra verification pass.
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

        assert captured_state.get("query_tier") == "tier4_deep"


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


@pytest.mark.asyncio
async def test_graph_stage_cache_disabled_coarse_factual_tier_rechecks_shape():
    """Cache-disabled requests must not let a coarse factual tier hide deep cues."""
    container = MagicMock()
    mock_fast_graph = AsyncMock()
    mock_fast_graph.nodes = {"handle_distress_check": {}, "handle_distress": {}}
    mock_standard_graph = AsyncMock()
    mock_deep_graph = AsyncMock()
    mock_deep_graph.ainvoke.return_value = {
        "final_answer": "deep answered",
        "citations": [],
        "intent": "FACTUAL",
    }
    container.fast_graph = mock_fast_graph
    container.standard_graph = mock_standard_graph
    container.deep_graph = mock_deep_graph
    coordinator = PipelineCoordinator(container)
    coordinator.coalescer = _DirectCoalescer()
    ctx = PipelineContext(
        container=container,
        coordinator=coordinator,
        request=MagicMock(),
        user_msg="Compare stillness with the beautiful state and explain how they relate.",
        preferred_lang="en",
        meditation_step=0,
        session_id="sess-deep-shape",
        user={"id": "user-1"},
        is_benchmark=True,
    )
    # Cache-disabled mode leaves this unset; the graph stage receives only the
    # coarse on-device factual hint and must re-check query shape.
    ctx.detected_query_tier = None
    ctx.preclassified_intent = "FACTUAL"
    ctx.preclassified_tier = "tier2_simple"
    ctx.preclassified_reason = "on_device_factual"
    ctx.state = {
        "user_msg_en": ctx.user_msg,
        "chat_history_en": [],
        "memory_context": "",
        "lang_detection": None,
        "query_tier": None,
        "intent": None,
    }
    with patch("rag.nodes.on_device_intent.classify_with_reason") as mock_classify:
        mock_classify.return_value = ("FACTUAL", "tier2_simple", "on_device_factual")
        with patch(
            "app.pipeline.stages.graph_stage.select_graph_for_query",
            new=AsyncMock(return_value="deep"),
        ) as mock_selector:
            await GraphStage().run(ctx)
    mock_selector.assert_awaited_once()
    assert mock_selector.await_args.kwargs["query_tier"] is None
    assert mock_deep_graph.ainvoke.called
    assert not mock_fast_graph.ainvoke.called


@pytest.mark.asyncio
async def test_timeout_budget_allocation_no_five_second_floor():
    """Criteria A3.3: TimeoutBudget must not floor to 5s on exhausted or low budget."""
    from rag.timeout_utils import TimeoutBudget

    # Budget is 0.0s (already exhausted)
    budget = TimeoutBudget(total_budget=0.0)
    assert budget.is_exhausted() is True
    allocated = budget.allocate("grade_documents", default_timeout=25.0)
    assert allocated == 0.0, f"Expected 0.0 allocated on exhausted budget, got {allocated}"

    # Budget is 1.5s
    budget_low = TimeoutBudget(total_budget=1.5)
    assert budget_low.is_exhausted() is False
    allocated_low = budget_low.allocate("grade_documents", default_timeout=25.0)
    assert allocated_low <= 1.5, f"Expected <= 1.5s allocated, got {allocated_low}"
    assert allocated_low > 0.0


@pytest.mark.asyncio
async def test_graph_stage_admission_deadline_propagation():
    """Criteria A3.4: Admission deadline propagation fails fast on expired deadline."""
    import time
    from unittest.mock import MagicMock

    container = MagicMock()
    mock_standard_graph = AsyncMock()
    container.standard_graph = mock_standard_graph
    container.fast_graph = mock_standard_graph
    container.deep_graph = mock_standard_graph

    coordinator = PipelineCoordinator(container)
    coordinator.coalescer = _DirectCoalescer()

    ctx = PipelineContext(
        container=container,
        coordinator=coordinator,
        request=MagicMock(),
        user_msg="What is the nature of consciousness?",
        preferred_lang="en",
        meditation_step=0,
        session_id="sess-timeout-1",
        user={"id": "user-1"},
        is_benchmark=False,
    )
    # Set start_time such that pipeline_timeout is already exceeded
    ctx.start_time = time.time() - (settings.pipeline_timeout + 10.0)
    ctx.state = {
        "user_msg_en": ctx.user_msg,
        "chat_history_en": [],
        "memory_context": "",
        "lang_detection": None,
        "query_tier": "standard",
        "intent": "QUERY",
    }

    stage = GraphStage()
    await stage.run(ctx)

    # Graph ainvoke should NOT be called since deadline was already expired
    assert not mock_standard_graph.ainvoke.called
    assert ctx.final_answer == "The Guru took too long to respond. Please try again."


@pytest.mark.asyncio
async def test_agentic_graph_traversal_reuses_injected_ollama_service(monkeypatch):
    """Criteria A3.2: agentic_graph_traversal must reuse injected container LLM service without instantiating OllamaService."""
    import sys
    import rag.nodes.agentic_graph_traversal
    from rag.nodes import _services

    agt = sys.modules["rag.nodes.agentic_graph_traversal"]

    mock_ollama_instance = AsyncMock()
    mock_ollama_instance._generate_fast.return_value = '{"action": "DONE", "reasoning": "done"}'
    monkeypatch.setattr(_services, "_ollama", mock_ollama_instance)

    with patch("services.ollama_service.OllamaService") as mock_ollama_cls:
        decision = await agt._ask_llm_to_decide(
            question="Compare karma and samsara",
            context_summary={"traversal_summary": "summary", "concepts_found": []},
            step=0,
            max_steps=3,
        )
        # Verify OllamaService was NOT freshly instantiated
        mock_ollama_cls.assert_not_called()
        # Verify the injected service was called
        mock_ollama_instance._generate_fast.assert_called_once()
        assert decision["action"] == "DONE"


@pytest.mark.asyncio
async def test_grade_documents_ambiguous_band_escalation(monkeypatch):
    """Criteria A3.5: Default grading to rerank confidence; escalate to LLM only for ambiguous band."""
    from rag.nodes import _services
    from rag.nodes.reranking import grade_documents

    mock_ollama = AsyncMock()
    mock_embedder = MagicMock()
    monkeypatch.setattr(_services, "_ollama", mock_ollama)
    monkeypatch.setattr(_services, "_embedder", mock_embedder)
    monkeypatch.setattr(settings, "crag_skip_confidence", 0.75)
    monkeypatch.setattr(settings, "rerank_min_score", 0.35)

    # 1. High confidence docs only -> NO LLM call
    state_high = {
        "query_tier": "tier3_complex",
        "question": "What is Ekam?",
        "reranked_docs": [
            {"text": "Doc 1", "rerank_score": 0.88, "source_url": "url1"},
            {"text": "Doc 2", "rerank_score": 0.82, "source_url": "url2"},
        ],
    }
    result_high = await grade_documents(state_high)
    assert len(result_high["relevant_docs"]) == 2
    mock_ollama.grade_relevance.assert_not_called()
    mock_ollama.batch_grade_relevance.assert_not_called()

    # 2. Ambiguous band docs -> LLM grading IS called
    mock_ollama.grade_relevance = AsyncMock(return_value=[{"relevant": True, "reason": "Good doc"}])
    state_ambiguous = {
        "query_tier": "tier3_complex",
        "question": "What is Ekam?",
        "reranked_docs": [
            {"text": "Doc Ambiguous", "rerank_score": 0.55, "source_url": "url3"},
        ],
    }
    result_ambiguous = await grade_documents(state_ambiguous)
    assert len(result_ambiguous["relevant_docs"]) == 1
    mock_ollama.grade_relevance.assert_called_once()


@pytest.mark.asyncio
async def test_retrieval_query_fan_out_limited_to_two(monkeypatch):
    """Criteria A3.5: Limit deep query fan-out from 6 to 2."""
    from rag.nodes import _services
    import rag.nodes as nodes

    mock_embedder = MagicMock()
    mock_embedder.encode_single_full.return_value = {"dense": [0.1] * 1024, "sparse": {"1": 0.5}}
    mock_embedder.encode_batch.return_value = {
        "dense": [[0.1] * 1024, [0.2] * 1024],
        "sparse": [{"1": 0.5}, {"2": 0.5}],
    }
    mock_embedder.instruction = "Retrieve: "

    mock_qdrant = MagicMock()
    mock_qdrant.search = MagicMock(return_value=[{"text": "Teaching doc", "source_url": "url1", "score": 0.9}])

    monkeypatch.setattr(_services, "_ollama", AsyncMock())
    monkeypatch.setattr(_services, "_embedder", mock_embedder)
    monkeypatch.setattr(_services, "_qdrant", mock_qdrant)
    monkeypatch.setattr(settings, "rag_okf_injection_enabled", False)
    monkeypatch.setattr(settings, "semantic_cache_enabled", False)
    monkeypatch.setattr(settings, "retrieval_score_delta_enabled", False)
    monkeypatch.setattr(settings, "rag_skip_retrieval_expansions", True)

    state = {
        "question": "Main query",
        "chat_history": [],
        "rewritten_query": None,
        "sub_queries": ["sub1", "sub2", "sub3", "sub4", "sub5"],
        "selected_clusters": [],
        "hyde_text": None,
        "intent": "QUERY",
        "query_tier": "tier3_complex",
    }

    res = await nodes.retrieve_documents(state)
    assert "evaluation_trace" in res
    retrieval_queries = res["evaluation_trace"].get("retrieval_queries", [])
    # Must be capped at 2 queries
    assert len(retrieval_queries) <= 2

