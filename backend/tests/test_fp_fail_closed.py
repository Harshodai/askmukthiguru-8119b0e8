"""T1-05 / T1-06: fail closed on the teaching route; no teacher register in general mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.pipeline.stages import first_person_bridge as bridge_module
from rag.nodes import first_person as fp_node_module
from services import fp_fail_closed
from tests.test_first_person_bridge import _container, _ctx


def _counter_value(reason: str) -> float:
    from app.metrics import FP_FAIL_CLOSED_TOTAL

    return FP_FAIL_CLOSED_TOTAL.labels(reason=reason)._value.get()


@pytest.fixture
def closed(monkeypatch):
    monkeypatch.setattr(settings, "fp_fail_closed_enabled", True)
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)


def _config(ctx):
    return {"configurable": {"pipeline_ctx": ctx}}


def test_predicate(monkeypatch):
    monkeypatch.setattr(settings, "fp_fail_closed_enabled", True)
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    assert fp_fail_closed.teaching_generation_allowed() is False
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", True)
    assert fp_fail_closed.teaching_generation_allowed() is True
    # Rollback flag restores the old behaviour.
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    monkeypatch.setattr(settings, "fp_fail_closed_enabled", False)
    assert fp_fail_closed.teaching_generation_allowed() is True


@pytest.mark.asyncio
async def test_bridge_off_returns_static_abstain_without_llm(closed, monkeypatch):
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", False)
    run = AsyncMock()
    monkeypatch.setattr(bridge_module, "run_first_person_bridge", run)
    before = _counter_value("fp_disabled")

    out = await fp_node_module.first_person_node({}, _config(_ctx(_container())))

    res = out["first_person_result"]
    assert res.route_decision == "first_person_abstain"
    assert res.model_used is None
    assert res.citations == []
    assert res.verification == {
        "passed": False,
        "method": "fp_disabled",
        "citations_verified": False,
    }
    run.assert_not_called()
    assert _counter_value("fp_disabled") == before + 1


@pytest.mark.asyncio
async def test_bridge_off_with_fallback_enabled_keeps_old_behaviour(monkeypatch):
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", False)
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", True)
    out = await fp_node_module.first_person_node({}, _config(_ctx(_container())))
    assert out == {}


@pytest.mark.asyncio
async def test_meditation_imperative_not_abstained_when_bridge_off(closed, monkeypatch):
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", False)
    out = await fp_node_module.first_person_node(
        {}, _config(_ctx(_container(), msg="guide me through a meditation"))
    )
    assert out == {}


@pytest.mark.asyncio
async def test_node_exception_abstains_and_counts(closed, monkeypatch):
    monkeypatch.setattr(bridge_module, "first_person_bridge_enabled", lambda: True)
    monkeypatch.setattr(
        bridge_module, "run_first_person_bridge", AsyncMock(side_effect=RuntimeError("boom"))
    )
    before = _counter_value("fp_node_error")

    out = await fp_node_module.first_person_node({}, _config(_ctx(_container())))

    res = out["first_person_result"]
    assert res.verification["method"] == "fp_node_error"
    assert res.verification["passed"] is False
    assert res.model_used is None
    assert _counter_value("fp_node_error") == before + 1


@pytest.mark.asyncio
async def test_node_exception_with_fallback_enabled_falls_through(monkeypatch):
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", True)
    monkeypatch.setattr(bridge_module, "first_person_bridge_enabled", lambda: True)
    monkeypatch.setattr(
        bridge_module, "run_first_person_bridge", AsyncMock(side_effect=RuntimeError("boom"))
    )
    out = await fp_node_module.first_person_node({}, _config(_ctx(_container())))
    assert out == {}


def test_registry_keeps_module_routable_when_bridge_off(closed, monkeypatch):
    from rag import pipeline_registry

    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", False)
    assert pipeline_registry._first_person_enabled() is True
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", True)
    assert pipeline_registry._first_person_enabled() is False


@pytest.mark.asyncio
async def test_generate_answer_guard_abstains_for_teaching_intent(closed, monkeypatch):
    from rag.nodes import generation

    llm = MagicMock()
    monkeypatch.setattr(generation._services, "_ollama", llm, raising=False)
    state = {
        "question": "how do I find peace?",
        "relevant_docs": [],
        "domain_route": "teaching",
        "intent": "QUERY",
    }
    before = _counter_value("generate_answer_guard")

    out = await generation.generate_answer(state)

    assert out["citations"] == []
    assert out["verification"] == {
        "passed": False,
        "method": "fp_disabled",
        "citations_verified": False,
    }
    assert out["answer"] == fp_fail_closed.STATIC_ABSTAIN_TEXT
    assert llm.method_calls == []
    assert _counter_value("generate_answer_guard") == before + 1
