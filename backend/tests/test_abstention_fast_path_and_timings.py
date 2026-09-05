"""Unit tests for P0-5 (Node Timing Instrumentation Coverage) and P0-6 (Abstention Fast-Path & Retry Elimination)."""

import pytest
from unittest.mock import AsyncMock, patch

from rag.graph_strategies import route_after_formatting
from rag.nodes.citation_extractor import extract_citations
from rag.nodes.cross_teacher_reasoning import cross_teacher_reasoning
from rag.nodes.generation import format_final_answer, generate_answer
from rag.nodes.intent import handle_casual, handle_distress, handle_meditation
from rag.nodes.retrieval import navigate_and_hyde
from rag.nodes.short_circuit import handle_fallback
from rag.nodes.verification import reflect_on_answer, verify_answer
from rag.nodes.web_search import web_search_node
from rag.states import GraphState


@pytest.mark.asyncio
async def test_zero_docs_abstention_fast_path_pipeline():
    """Verify that generate_answer with 0 docs passes through verification and formatting without setting _needs_retry=True."""
    state: GraphState = {
        "question": "What is quantum gravity according to the gurus?",
        "relevant_docs": [],
        "documents": [],
        "query_tier": "standard",
        "chat_history": [],
        "retry_count": 0,
        "metrics": {},
        "node_timings": {},
    }

    # Step 1: generate_answer with 0 docs should short-circuit to abstention
    gen_result = await generate_answer(state)
    assert gen_result["grounding_state"] == "abstained"
    assert gen_result["verification"]["method"] == "no_context_short_circuit"
    assert "node_timings" in gen_result
    assert "generate_answer" in gen_result["node_timings"]

    # Merge into state
    state.update(gen_result)

    # Step 2: reflect_on_answer should fast-pass immediately without LLM/LettuceDetect calls
    reflect_result = await reflect_on_answer(state)
    assert reflect_result["is_valid"] is True
    assert reflect_result["needs_correction"] is False
    assert reflect_result["grounding_state"] == "abstained"
    assert reflect_result["verification"]["passed"] is True
    assert reflect_result["verification"]["method"] == "no_context_short_circuit"
    assert "node_timings" in reflect_result
    assert "reflect_on_answer" in reflect_result["node_timings"]

    state.update(reflect_result)

    # Step 3: verify_answer should fast-pass immediately
    verify_result = await verify_answer(state)
    assert verify_result["is_valid"] is True
    assert verify_result["needs_correction"] is False
    assert verify_result["grounding_state"] == "abstained"
    assert verify_result["verification"]["passed"] is True
    assert verify_result["verification"]["method"] == "no_context_short_circuit"
    assert "node_timings" in verify_result
    assert "verify_answer" in verify_result["node_timings"]

    state.update(verify_result)

    # Step 4: format_final_answer should NOT set _needs_retry=True
    format_result = await format_final_answer(state)
    assert format_result["_needs_retry"] is False
    assert format_result["grounding_state"] == "abstained"
    assert format_result["verification"]["passed"] is True
    assert "final_answer" in format_result
    assert len(format_result["final_answer"]) > 0
    assert "node_timings" in format_result
    assert "format_final_answer" in format_result["node_timings"]
    assert isinstance(format_result["node_timings"]["format_final_answer"], float)

    state.update(format_result)

    # Step 5: route_after_formatting must route directly to 'end'
    next_node = route_after_formatting(state)
    assert next_node == "end"


@pytest.mark.asyncio
async def test_format_final_answer_node_timings_recorded():
    """Verify that format_final_answer execution time is recorded in node_timings."""
    state: GraphState = {
        "question": "What is the beautiful state?",
        "answer": "The beautiful state is a state of connection and peace.",
        "relevant_docs": [
            {
                "title": "Beautiful State",
                "text": "The beautiful state is a state of connection and peace.",
                "source_url": "https://www.youtube.com/watch?v=example123",
            }
        ],
        "citations": [{"url": "https://www.youtube.com/watch?v=example123", "title": "Beautiful State"}],
        "is_faithful": True,
        "verification": {"passed": True, "method": "local_nli"},
        "confidence_score": 9.0,
        "faithfulness_score": 0.95,
        "query_tier": "fast",
        "retry_count": 0,
        "metrics": {},
        "node_timings": {},
    }

    result = await format_final_answer(state)
    assert "node_timings" in result
    assert "format_final_answer" in result["node_timings"]
    assert result["node_timings"]["format_final_answer"] >= 0.0


@pytest.mark.asyncio
async def test_node_timing_instrumentation_coverage():
    """Verify all newly instrumented nodes record their duration in node_timings."""
    base_state: GraphState = {
        "question": "Hello guru",
        "chat_history": [],
        "relevant_docs": [],
        "documents": [],
        "query_tier": "standard",
        "retry_count": 0,
        "metrics": {},
        "node_timings": {},
    }

    # 1. extract_citations
    state_citations = {
        **base_state,
        "answer": "This is a profound teaching on meditation.",
        "relevant_docs": [{"text": "This is a profound teaching on meditation.", "source_url": "https://example.com"}],
    }
    cit_res = extract_citations(state_citations)
    assert "node_timings" in cit_res
    assert "extract_citations" in cit_res["node_timings"]

    # 2. handle_casual
    cas_res = await handle_casual(base_state)
    assert "node_timings" in cas_res
    assert "handle_casual" in cas_res["node_timings"]
    assert cas_res.get("intent") == "CASUAL"
    assert cas_res.get("route_decision") == "casual"

    # 3. handle_distress
    distress_state = {**base_state, "question": "I am feeling overwhelmed and sad."}
    with patch("rag.nodes.intent._services._serene_mind", None), patch(
        "rag.nodes.intent._services._ollama", None
    ):
        dist_res = await handle_distress(distress_state)
        assert "node_timings" in dist_res
        assert "handle_distress" in dist_res["node_timings"]
        assert dist_res.get("intent") == "DISTRESS"
        assert dist_res.get("route_decision") == "distress"

    # 4. handle_meditation
    med_state = {**base_state, "question": "Guide me through Soul Sync meditation", "meditation_step": 0}
    med_res = await handle_meditation(med_state)
    assert "node_timings" in med_res
    assert "handle_meditation" in med_res["node_timings"]
    assert med_res.get("intent") == "MEDITATION"
    assert med_res.get("route_decision") == "meditation"

    # 5. handle_fallback
    fb_res = await handle_fallback(base_state)
    assert "node_timings" in fb_res
    assert "handle_fallback" in fb_res["node_timings"]
    assert fb_res.get("route_decision") == "no_context_short_circuit"

    # 6. cross_teacher_reasoning
    ct_state = {**base_state, "question": "What is the difference between Sadhguru and Sri Krishnaji?"}
    with patch("rag.nodes.cross_teacher_reasoning._get_driver", return_value=None):
        ct_res = await cross_teacher_reasoning(ct_state)
        assert "node_timings" in ct_res
        assert "cross_teacher_reasoning" in ct_res["node_timings"]

    # 7. web_search_node
    ws_state = {**base_state, "intent": "LIVE_LOGISTICS"}
    with patch("rag.nodes.web_search.settings.live_logistics_enabled", False):
        ws_res = await web_search_node(ws_state)
        assert "node_timings" in ws_res
        assert "web_search_node" in ws_res["node_timings"]

    # 8. navigate_and_hyde
    nh_state = {**base_state}
    with patch("rag.nodes.retrieval.navigate_knowledge_tree", AsyncMock(return_value={"tree_docs": []})), patch(
        "rag.nodes.retrieval.generate_hyde", AsyncMock(return_value={"hyde_doc": "mock"})
    ):
        nh_res = await navigate_and_hyde(nh_state)
        assert "node_timings" in nh_res
        assert "navigate_and_hyde" in nh_res["node_timings"]
