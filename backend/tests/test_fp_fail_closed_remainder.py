"""SYS-001 remainder (T1-05): classifier failure and a context-free node call.

With generation not deliberately allowed (``fail_closed_active``), a broken
domain classifier must not send a teaching question to the generating general
lane, and a graph call with no pipeline context must not reach generation
either. With generation allowed (rollback), the old routing stays.
"""

from __future__ import annotations

import pytest

import app.pipeline.stages.off_topic_stage as off_topic
from app.config import settings
from app.pipeline.stages.graph_stage import select_general_knowledge_mode
from rag import pipeline_registry
from rag.nodes import first_person as fp_node_module


def _boom(_q: str) -> bool:
    raise RuntimeError("classifier import failed")


def _counter(reason: str) -> float:
    from app.metrics import FP_FAIL_CLOSED_TOTAL

    return FP_FAIL_CLOSED_TOTAL.labels(reason=reason)._value.get()


@pytest.fixture
def closed(monkeypatch):
    monkeypatch.setattr(settings, "fp_fail_closed_enabled", True)
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)


@pytest.fixture
def generation_allowed(monkeypatch):
    monkeypatch.setattr(settings, "fp_fail_closed_enabled", True)
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", True)


def test_classifier_failure_keeps_the_teaching_lane_when_closed(closed, monkeypatch):
    monkeypatch.setattr(off_topic, "is_spiritual_domain_query", _boom)
    before = _counter("domain_classifier_error")

    assert select_general_knowledge_mode({}, "how do I stop suffering?") is False
    assert _counter("domain_classifier_error") == before + 1


def test_classifier_failure_keeps_old_routing_when_generation_allowed(
    generation_allowed, monkeypatch
):
    monkeypatch.setattr(off_topic, "is_spiritual_domain_query", _boom)
    assert select_general_knowledge_mode({}, "how do I stop suffering?") is True


def test_upstream_decisions_still_win(closed, monkeypatch):
    monkeypatch.setattr(off_topic, "is_spiritual_domain_query", _boom)
    assert select_general_knowledge_mode({"general_knowledge_mode": True}, "q") is True
    assert select_general_knowledge_mode({"domain_route": "teaching"}, "q") is False


def test_classifier_success_is_unchanged(closed, monkeypatch):
    monkeypatch.setattr(off_topic, "is_spiritual_domain_query", lambda q: False)
    assert select_general_knowledge_mode({}, "capital of France?") is True
    monkeypatch.setattr(off_topic, "is_spiritual_domain_query", lambda q: True)
    assert select_general_knowledge_mode({}, "what is the beautiful state?") is False


def test_registry_claims_the_turn_when_the_classifier_fails_closed(closed, monkeypatch):
    monkeypatch.setattr(off_topic, "is_spiritual_domain_query", _boom)
    assert pipeline_registry._first_person_claims({"question": "why do I suffer?"}) is True


def test_registry_falls_to_general_when_generation_allowed(generation_allowed, monkeypatch):
    monkeypatch.setattr(off_topic, "is_spiritual_domain_query", _boom)
    assert pipeline_registry._first_person_claims({"question": "why do I suffer?"}) is False


@pytest.mark.asyncio
async def test_node_without_pipeline_context_abstains_when_closed(closed):
    before = _counter("no_pipeline_ctx")

    out = await fp_node_module.first_person_node({"question": "why do I suffer?"}, None)

    res = out["first_person_result"]
    assert res.route_decision == "first_person_abstain"
    assert res.model_used is None and res.citations == []
    assert res.verification["passed"] is False
    assert out["final_answer"] == res.final_answer
    assert out["verification"] == res.verification
    assert _counter("no_pipeline_ctx") == before + 1


@pytest.mark.asyncio
async def test_node_without_pipeline_context_falls_through_when_generation_allowed(
    generation_allowed,
):
    assert await fp_node_module.first_person_node({"question": "q"}, None) == {}
