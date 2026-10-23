"""Route safety tests for observational first-person context shadow evaluation."""

import time
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import get_container_async
from app.main import app
from services.first_person_context_harness import (
    record_shadow_outcome,
    reset_harness_metrics,
    shadow_metrics_snapshot,
)
from services.first_person_pipeline import FirstPersonPipelineResult

import app.api.first_person as first_person_route

client = TestClient(app)


class _PassRail:
    async def check_output(self, _text):
        return {"blocked": False, "reason": None}


class _Embedding:
    async def encode_single_full_async(self, _text):
        return {"dense": [0.1] * 1024, "sparse": {}}


class _Container:
    embedding = _Embedding()
    guardrails = _PassRail()


def _result(status="success"):
    citations = []
    if status == "success":
        citations = [
            {
                "video_id": "vid1",
                "start_ms": 1000,
                "end_ms": 2000,
                "timestamp_seconds": 1,
                "speaker": "Sri Preethaji",
                "teacher_id": "preethaji",
                "transcript_hash": "a" * 64,
                "verbatim_text": "Exact stored teaching.",
                "source_url": "https://youtube.com/watch?v=vid1",
                "video_url": "https://youtube.com/watch?v=vid1",
                "text_snippet": "Exact stored teaching.",
                "confidence": 0.9,
                "is_verbatim": True,
                "provenance_kind": "speech_turn_clip",
                "caption_status": "auto_transcript",
            }
        ]
    return FirstPersonPipelineResult(
        answer_text="Exact stored teaching." if status == "success" else "Safety response.",
        citations=citations,
        status=status,
        is_direct_answer=status == "success",
        latency_ms=12.0,
    )


def _install_route(monkeypatch, status="success"):
    pipeline = Mock()
    pipeline.execute.return_value = _result(status)
    monkeypatch.setattr(first_person_route, "_pipeline", lambda *args: pipeline)
    app.dependency_overrides[get_container_async] = lambda: _Container()
    return pipeline


def _post():
    return client.post(
        "/api/first-person/query",
        json={"query": "What is suffering?", "teacher_id": "preethaji"},
    )


def _drain_shadow_tasks(timeout: float = 5.0) -> None:
    """Wait for the fire-and-forget observer scheduled by the route."""
    deadline = time.monotonic() + timeout
    while first_person_route._SHADOW_TASKS and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not first_person_route._SHADOW_TASKS, "shadow task did not finish"


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    _drain_shadow_tasks()
    reset_harness_metrics()
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_shadow_enabled", False)
    monkeypatch.setattr(settings, "first_person_context_collection", "")
    yield
    _drain_shadow_tasks()
    app.dependency_overrides.pop(get_container_async, None)


def test_shadow_flag_off_then_on_does_not_change_route_response(monkeypatch):
    _install_route(monkeypatch)
    monkeypatch.setattr(
        first_person_route,
        "_evaluate_context_shadow",
        lambda *_args: pytest.fail("shadow evaluator called while feature flag is off"),
    )
    response_off = _post()
    assert response_off.status_code == 200
    assert shadow_metrics_snapshot() == {}

    monkeypatch.setattr(settings, "first_person_context_shadow_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_collection", "fp_context_v1_candidate")
    evaluator = Mock(return_value="evaluated")
    monkeypatch.setattr(first_person_route, "_evaluate_context_shadow", evaluator)
    response_on = _post()

    assert response_on.status_code == 200
    assert response_on.json() == response_off.json()
    _drain_shadow_tasks()
    evaluator.assert_called_once_with([0.1] * 1024, "preethaji")
    assert shadow_metrics_snapshot() == {"evaluated": 1}


def test_crisis_and_nonstandard_statuses_never_enter_shadow(monkeypatch):
    _install_route(monkeypatch, status="safety_redirect")
    monkeypatch.setattr(settings, "first_person_context_shadow_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_collection", "fp_context_v1_candidate")
    monkeypatch.setattr(
        first_person_route,
        "_evaluate_context_shadow",
        lambda *_args: pytest.fail("safety status reached the shadow evaluator"),
    )

    response = _post()

    assert response.status_code == 200
    assert response.json()["status"] == "safety_redirect"
    assert shadow_metrics_snapshot() == {}


def test_shadow_failure_is_fail_open_and_does_not_change_response(monkeypatch):
    _install_route(monkeypatch)
    monkeypatch.setattr(settings, "first_person_context_shadow_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_collection", "fp_context_v1_candidate")
    monkeypatch.setattr(
        first_person_route,
        "_evaluate_context_shadow",
        Mock(side_effect=RuntimeError("contains question text: What is suffering?")),
    )

    response = _post()

    assert response.status_code == 200
    assert response.json()["answer_text"] == "Exact stored teaching."
    _drain_shadow_tasks()
    assert shadow_metrics_snapshot() == {"error": 1}


def test_shadow_metric_labels_cannot_carry_request_text():
    record_shadow_outcome("user-query-or-source-text")
    record_shadow_outcome("timeout")

    assert shadow_metrics_snapshot() == {"error": 1, "timeout": 1}


def test_shadow_evaluator_reads_one_candidate_and_forces_indeterminate_answerability(monkeypatch):
    from services import first_person_context_harness as harness_module

    monkeypatch.setattr(settings, "first_person_context_collection", "fp_context_v1_candidate")
    context = object()
    store = Mock()
    store.retrieve.return_value = [context]
    monkeypatch.setattr(first_person_route, "_context_shadow_store", lambda *_args: store)

    class _Harness:
        def __init__(self, policy):
            assert policy == "bounded-policy"

        def decide(self, candidate, **kwargs):
            assert candidate is context
            assert kwargs == {
                "requested_teacher": "preethaji",
                "answerability": "indeterminate",
            }
            return object()  # Deliberately discarded by the route.

    monkeypatch.setattr(harness_module, "FirstPersonContextHarness", _Harness)
    monkeypatch.setattr(harness_module, "policy_from_settings", lambda: "bounded-policy")

    outcome = first_person_route._evaluate_context_shadow([0.25] * 1024, "preethaji")

    assert outcome == "evaluated"
    store.retrieve.assert_called_once_with(
        [0.25] * 1024,
        guru_id="preethaji",
        limit_parents=1,
        spans_per_parent=3,
    )
