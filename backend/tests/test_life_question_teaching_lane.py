"""Life questions must reach the first-person route, never LLM prose (invariants 2, 21).

Live failure: "My wife and I fight every day" etc. got general_knowledge_unverified
deepseek prose. OffTopicStage correctly chose the teaching lane, but GraphStage
re-derived general_knowledge_mode from a keyword classifier and overrode it, and
the registry's first_person ``claims`` used the same classifier. These tests run
the real stage chain (OffTopicStage -> GraphStage -> registry), not one stage.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.stages import GraphStage
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.off_topic_stage import OffTopicStage
from rag.pipeline_registry import select_pipeline
from services.attribution import clean_wire_speaker
from services.first_person_pipeline import _passes_integrity_gate

LIFE_QUESTIONS = [
    "My wife and I fight every day, what do I do?",
    "I feel lost and empty, what should I do?",
    "I am so lonely",
    "मेरी पत्नी और मैं रोज़ लड़ते हैं, क्या करूँ?",
]


class _DirectCoalescer:
    async def get_or_run(self, key, callback):
        return await callback()


@pytest.mark.asyncio
@pytest.mark.parametrize("question", LIFE_QUESTIONS)
async def test_life_question_stays_on_teaching_lane_through_stage_chain(monkeypatch, question):
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")

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

    # Jev unavailable (the live TimeoutError): must default to teaching, not general.
    with patch(
        "services.jev_router_service.JevRouterService.classify",
        new=AsyncMock(side_effect=TimeoutError()),
    ):
        await OffTopicStage().run(ctx)
    await GraphStage().run(ctx)

    initial_state = graph.ainvoke.call_args.args[0]
    assert initial_state["general_knowledge_mode"] is False
    assert initial_state["domain_route"] == "teaching"
    assert select_pipeline(initial_state).name == "first_person"


def test_unrouted_secular_state_is_not_claimed_by_first_person(monkeypatch):
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    state = {"question": "What is the capital of France?", "general_knowledge_mode": True}
    assert select_pipeline(state).name == "general"


def test_integrity_gate_rejects_non_allowlisted_speaker_and_wire_label_is_downgrade():
    import hashlib

    text = "I invite you to rest in this moment and let the breath settle fully into you."
    clip = {
        "verbatim_text": text,
        "transcript_hash": hashlib.sha256(text.encode()).hexdigest(),
        "speaker": "shared in Times Now",
        "video_id": "x",
    }
    assert _passes_integrity_gate(clip, check_availability=False) is False
    # A stored allowlisted-but-unverified clip ships only as the honest downgrade label.
    assert clean_wire_speaker("Sri Krishnaji", None, "Times Now") == "shared in Times Now"
