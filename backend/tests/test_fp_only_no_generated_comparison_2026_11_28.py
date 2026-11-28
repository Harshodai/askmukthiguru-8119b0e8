"""Fallback off: a comparison question never reaches LLM-written prose (invariant 21).

Live 2026-11-28: "difference between a mantra and a prayer" was handed to the graph by
the bridge, and the graph's Jev router flipped it into the general lane.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.config import settings

Q = "What is the difference between a mantra and a prayer?"


@pytest.mark.asyncio
async def test_bridge_abstains_on_difference_question_when_fallback_off(monkeypatch):
    from app.pipeline.stages.context import PipelineContext
    from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
    from app.schemas import ChatRequest

    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=ChatRequest(messages=[], user_message=Q),
        user_msg=Q,
        preferred_lang="en",
        trace_id="t-diff",
        state={"user_msg_en": Q},
    )
    res = await FirstPersonBridgeStage().run(ctx)
    assert res is not None, "bridge must not hand a comparison to the generating graph"
    assert res.model_used is None
    assert res.route_decision != "general_knowledge_unverified"


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback,expect_general", [(False, False), (True, True)])
async def test_intent_node_jev_general_route_respects_fallback_flag(
    monkeypatch, fallback, expect_general
):
    from rag.nodes import intent as intent_mod

    intent_mod._intent_classification_cache.clear()
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", fallback)
    monkeypatch.setattr(settings, "intent_router_jev_enabled", True)
    monkeypatch.setattr(settings, "jev_enabled", True)

    class _Jev:
        def __init__(self, *a, **k): ...

        async def classify(self, q):
            return {
                "intent": "COMPARATIVE",
                "query_tier": "tier3_complex",
                "confidence": 0.95,
                "domain_route": "general",
                "needs_web_search": False,
            }

    monkeypatch.setattr("services.jev_router_service.JevRouterService", _Jev)
    out = await intent_mod._intent_router_impl(
        {"question": Q, "chat_history": [], "messages": []}, None
    )
    assert out["general_knowledge_mode"] is expect_general
    assert out["domain_route"] == ("general" if expect_general else "teaching")
