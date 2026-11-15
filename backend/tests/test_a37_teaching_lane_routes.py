"""A-37: with FIRST_PERSON_LLM_FALLBACK_ENABLED=false no teaching question reaches generated prose.

Routes traced (2026-11-15). OffTopicStage writes ``domain_route=teaching`` into
``ctx.state`` on some branches only; the explicit-teaching (``off_topic_stage.py``
440-444) and plain spiritual-candidate (580-582) branches set it in route metadata
alone, so the ``generate_answer`` guard (``generation.py`` 2676) cannot fire for them.
They stay closed because ``is_spiritual_domain_query`` is True whenever
``has_explicit_teaching_intent`` is (``off_topic_stage.py`` 311/319): the turn is not
general-knowledge, the first-person module claims it, and any non-served first-person
result ends the graph (``graph_strategies._route_after_first_person``). These tests
run the real stages, not the predicates in isolation.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.graph import END

from app.config import settings
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.stages import GraphStage
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.off_topic_stage import OffTopicStage
from rag.graph_strategies import _route_after_first_person
from rag.pipeline_registry import select_pipeline

_BACKEND = Path(__file__).resolve().parents[1]

# Teacher-attributed questions on secular topics: the case a review flagged as a
# possible general-lane leak with teacher attribution.
TEACHING_QUESTIONS = [
    "What does Sri Krishnaji say about the stock market?",
    "According to Sri Preethaji, which phone should I buy?",
    "Quote Sri Preethaji on football",
    "What is the beautiful state?",
    "How do I stop suffering?",
]


class _DirectCoalescer:
    async def get_or_run(self, key, callback):
        return await callback()


@pytest.fixture
def fp_only(monkeypatch):
    monkeypatch.setattr(settings, "fp_fail_closed_enabled", True)
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")


@pytest.mark.asyncio
@pytest.mark.parametrize("question", TEACHING_QUESTIONS)
async def test_teaching_question_is_claimed_by_first_person(fp_only, question):
    graph = AsyncMock()
    graph.nodes = {"handle_distress_check": {}, "handle_distress": {}}
    graph.ainvoke.return_value = {"final_answer": "x", "citations": [], "intent": "FACTUAL"}
    container = MagicMock()
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

    with patch(
        "services.jev_router_service.JevRouterService.classify",
        new=AsyncMock(side_effect=TimeoutError()),
    ):
        assert await OffTopicStage().run(ctx) is None
    await GraphStage().run(ctx)

    initial_state = graph.ainvoke.call_args.args[0]
    assert initial_state["general_knowledge_mode"] is False
    assert select_pipeline(initial_state).name == "first_person"


@pytest.mark.parametrize(
    "metadata",
    [
        {"abstain_cause": "no_evidence"},
        {"abstain_cause": "system_unavailable"},
        {"abstain_cause": "something_new"},
        {},
    ],
)
def test_every_non_served_first_person_result_ends_the_graph(fp_only, metadata):
    result = SimpleNamespace(route_metadata=metadata)
    assert _route_after_first_person({"first_person_result": result}) == END


def test_deep_research_never_writes_an_answer():
    """deep_research gathers documents (its LLM call is a sufficiency judge); it is
    reached only from retrieval, upstream of the guarded generate_answer."""
    tree = ast.parse((_BACKEND / "rag" / "nodes" / "deep_research.py").read_text())
    keys = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not keys & {"answer", "final_answer"}

    callers = [
        p.relative_to(_BACKEND).as_posix()
        for p in (_BACKEND / "rag").rglob("*.py")
        if "conduct_deep_research(" in p.read_text(encoding="utf-8")
    ]
    assert sorted(callers) == ["rag/nodes/deep_research.py", "rag/nodes/retrieval.py"]
