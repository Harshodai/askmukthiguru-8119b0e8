"""A-34: no general-lane prose on the first-person-only posture (invariant 21).

Measured 2026-11-15 (real stages, providers stubbed). With
``FIRST_PERSON_LLM_FALLBACK_ENABLED`` off, two general-task shapes reached the
generating general lane and got model-written prose (one provider call, answer =
provider text, ``grounding_state="unverified"``):

  * an inner-help word on a general task — ``_is_general_task`` returns False
    when every task-cue match is a soft context, so the turn fell past the
    domain-boundary refusal ("My mind keeps overthinking, can you write an email
    to my boss asking for leave?");
  * a guided-practice cue on a general task — the ``_GUIDED_PRACTICE_RE`` early
    return skipped the general-lane decision entirely ("Walk me through filing my
    tax return").

The third probe example ("I'm worried about my Python code, can you debug it?")
is NOT a leak: the on-device distress classifier and ``assess_distress`` both fire,
``route_after_intent`` sends it to ``handle_distress`` and the seeker gets the
static compassion template with no provider call. That is the documented
MODERATE+ distress carve-out and these tests pin it as unchanged.

Each test runs the real ``DistressStage``, ``OffTopicStage``, ``GraphStage``,
``select_pipeline``, ``route_after_intent`` and generation/distress node; only the
graph's ``ainvoke`` and the LLM providers are stubbed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.stages import GraphStage
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.distress_stage import DistressStage
from app.pipeline.stages.off_topic_stage import OffTopicStage, build_off_topic_response
from rag.graph_strategies import route_after_intent
from rag.pipeline_registry import select_pipeline
from services.serene_mind_engine import DistressLevel

DISTRESS_EXAMPLE = "I'm worried about my Python code, can you debug it?"
LEAK_EXAMPLES = [
    "My mind keeps overthinking, can you write an email to my boss asking for leave?",
    "Walk me through filing my tax return",
]


class _DirectCoalescer:
    async def get_or_run(self, key, callback):
        return await callback()


@pytest.fixture
def fp_only(monkeypatch):
    """First-person-only posture: bridge on, generated fallback off."""
    monkeypatch.setattr(settings, "fp_fail_closed_enabled", True)
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", False)
    monkeypatch.setattr(settings, "distress_llm_escalation_enabled", False)


def _ctx(question: str) -> PipelineContext:
    graph = AsyncMock()
    graph.nodes = {"handle_distress_check": {}, "handle_distress": {}}
    graph.ainvoke.return_value = {"final_answer": "x", "citations": [], "intent": "FACTUAL"}
    container = MagicMock()
    container.serene_mind = None
    container.ollama = None
    container.fast_graph = container.standard_graph = container.deep_graph = graph
    coordinator = PipelineCoordinator(container)
    coordinator.coalescer = _DirectCoalescer()
    ctx = PipelineContext(
        container=container,
        coordinator=coordinator,
        request=MagicMock(),
        user_msg=question,
        preferred_lang="en",
        meditation_step=0,
        session_id="s",
        user={"id": "u"},
        is_benchmark=False,
    )
    ctx.state = {"user_msg_en": question, "chat_history_en": [], "memory_context": ""}
    return ctx


async def _chain(question: str):
    """Real DistressStage -> OffTopicStage -> GraphStage; returns (ctx, graph)."""
    ctx = _ctx(question)
    assert await DistressStage().run(ctx) is None
    off_topic_result = await OffTopicStage().run(ctx)
    if off_topic_result is not None:
        return ctx, None, off_topic_result
    await GraphStage().run(ctx)
    return ctx, ctx.container.fast_graph, None


@pytest.mark.asyncio
async def test_moderate_distress_example_keeps_its_carve_out(fp_only):
    """Example 1 is the documented MODERATE+ distress carve-out, not a leak."""
    from rag.nodes.intent import handle_distress

    ctx, graph, off_topic_result = await _chain(DISTRESS_EXAMPLE)
    assert ctx.assessment is not None
    assert ctx.assessment.level.value >= DistressLevel.MODERATE.value
    # The distress carve-out is why OffTopicStage does not refuse this turn.
    assert off_topic_result is None

    initial_state = graph.ainvoke.call_args.args[0]
    # The intent stage classified this turn DISTRESS (measured 2026-11-15).
    assert route_after_intent({**initial_state, "intent": "DISTRESS"}) == "distress"

    from rag.nodes import intent as intent_node

    llm = MagicMock()
    with (
        patch.object(intent_node._services, "_serene_mind", None, create=True),
        patch.object(intent_node._services, "_ollama", llm, create=True),
    ):
        out = await handle_distress({**initial_state, "intent": "DISTRESS"})
    assert out["final_answer"]
    assert out["route_decision"] == "distress"
    assert out["citations"] == []
    assert llm.method_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("question", LEAK_EXAMPLES)
async def test_general_task_is_refused_without_generated_prose(fp_only, question):
    """Both blind spots now get the existing static domain-boundary refusal."""
    ctx, graph, result = await _chain(question)
    assert result is not None
    # A returned PipelineResult ends the turn before GraphStage.
    assert graph is None
    assert result.route_decision == "off_topic_domain_boundary"
    assert result.final_answer == build_off_topic_response()
    assert result.citations == []
    assert result.model_used is None and result.model_provider is None
    assert result.verification["grounding_state"] == "abstained"
    assert ctx.state.get("general_knowledge_mode") is not True


@pytest.mark.asyncio
async def test_boundary_off_fallback_off_keeps_turn_on_teaching_lane(fp_only, monkeypatch):
    """Boundary refusal disabled: fail closed to the teaching lane, never prose."""
    import app.pipeline.stages.off_topic_stage as off_topic_mod
    from rag.nodes import generation

    monkeypatch.setattr(off_topic_mod, "off_topic_domain_boundary_enabled", lambda: False)
    llm = MagicMock()
    monkeypatch.setattr(generation._services, "_ollama", llm, raising=False)

    question = LEAK_EXAMPLES[0]
    ctx, graph, result = await _chain(question)
    assert result is None
    initial_state = graph.ainvoke.call_args.args[0]
    assert initial_state.get("general_knowledge_mode") is not True
    assert initial_state.get("domain_route") == "teaching"
    assert select_pipeline(initial_state).name == "first_person"
    assert route_after_intent({**initial_state, "intent": "FACTUAL"}) == "query"

    out = await generation.generate_answer(
        {**initial_state, "intent": "FACTUAL", "relevant_docs": []}
    )
    assert out["verification"]["method"] == "fp_disabled"
    assert llm.method_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("question", [DISTRESS_EXAMPLE, *LEAK_EXAMPLES])
async def test_general_assistant_mode_still_generates(fp_only, question, monkeypatch):
    """Fallback on: byte-for-byte the old behaviour (general lane, one LLM call)."""
    from rag.nodes import generation

    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", True)
    llm = MagicMock()
    llm.generate = AsyncMock(return_value="Generated answer text.")
    monkeypatch.setattr(generation._services, "_ollama", llm, raising=False)

    ctx, graph, result = await _chain(question)
    assert result is None
    initial_state = graph.ainvoke.call_args.args[0]
    assert initial_state.get("general_knowledge_mode") is True
    assert route_after_intent({**initial_state, "intent": "FACTUAL"}) == "general"

    out = await generation.generate_answer(
        {**initial_state, "intent": "FACTUAL", "relevant_docs": []}
    )
    assert llm.generate.await_count == 1
    assert "Generated answer text." in out["answer"]
