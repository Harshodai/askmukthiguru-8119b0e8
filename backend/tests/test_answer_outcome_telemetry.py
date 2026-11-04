"""T2-03: answer_outcome record and metrics."""

import json

from app.answer_outcome import build_answer_outcome, emit_answer_outcome
from app.metrics import ANSWER_OUTCOME_TOTAL, INTEGRITY_BREACH_TOTAL

SEEKER = "my secret question about grief"
ANSWER = "verbatim teaching text"


def _rec(**kw):
    base = dict(
        request_id="t1",
        route_decision="first_person_bridge",
        route_reason="fp",
        grounding_state="grounded",
        citations=[{"clip_id": "c1"}, {"point_id": "p2"}],
        verification={"passed": True, "method": "sha256", "citations_verified": True},
        cache_hit=False,
        latency_ms=1200,
        model_used=None,
    )
    base.update(kw)
    return build_answer_outcome(**base)


def _count(lane, outcome):
    return ANSWER_OUTCOME_TOTAL.labels(lane=lane, outcome=outcome)._value.get()


def test_served():
    r = _rec()
    assert (r["lane"], r["outcome"]) == ("first_person", "served")
    assert r["span_ids"] == ["c1", "p2"] and r["citation_count"] == 2
    assert r["verification_method"] == "sha256" and r["verification_passed"] is True
    before = _count("first_person", "served")
    emit_answer_outcome(r, first_person_only=True)
    assert _count("first_person", "served") == before + 1


def test_abstained():
    r = _rec(grounding_state="abstained", citations=[])
    assert r["outcome"] == "abstained" and r["span_ids"] == []


def test_crisis():
    assert _rec(route_decision="distress")["outcome"] == "crisis"


def test_error():
    assert _rec(route_decision="query", errored=True)["outcome"] == "error"
    assert _rec(route_decision="error")["lane"] == "error"


def test_no_seeker_text_or_ids():
    r = _rec()
    blob = json.dumps(r)
    assert SEEKER not in blob and ANSWER not in blob
    for k in ("user_id", "session_id", "message", "answer", "final_answer"):
        assert k not in r


def test_integrity_breach_counter():
    gen = _rec(route_decision="query", model_used="deepseek/deepseek-chat")
    before = INTEGRITY_BREACH_TOTAL.labels(lane="teaching")._value.get()
    emit_answer_outcome(gen, first_person_only=False)
    assert INTEGRITY_BREACH_TOTAL.labels(lane="teaching")._value.get() == before
    emit_answer_outcome(gen, first_person_only=True)
    assert INTEGRITY_BREACH_TOTAL.labels(lane="teaching")._value.get() == before + 1
    emit_answer_outcome(_rec(), first_person_only=True)  # verbatim: no breach
    assert INTEGRITY_BREACH_TOTAL.labels(lane="teaching")._value.get() == before + 1


def test_emit_never_raises():
    emit_answer_outcome({}, first_person_only=True)


# --- every terminal path emits exactly one outcome (coordinator wrapper) ---


def _coordinator():
    from unittest.mock import MagicMock

    from app.pipeline.pipeline_coordinator import PipelineCoordinator

    return PipelineCoordinator(MagicMock())


def _run_execute(result):
    import asyncio
    from unittest.mock import AsyncMock, patch

    coord = _coordinator()
    with (
        patch.object(coord, "_execute_stages", AsyncMock(return_value=result)) as inner,
        patch("app.answer_outcome.emit_answer_outcome") as emit,
    ):
        out = asyncio.run(coord.execute(user_msg="x", preferred_lang="en", chat_body=None))
    assert inner.await_count == 1
    return out, emit


def test_cache_hit_emits_one_outcome_with_cache_hit_true():
    from app.pipeline.result import PipelineResult

    res = PipelineResult(
        final_answer="cached",
        trace_id="t1",
        route_decision="first_person_bridge",
        cache_hit=True,
        model_used=None,
    )
    out, emit = _run_execute(res)
    assert out is res
    assert emit.call_count == 1
    record = emit.call_args.args[0]
    assert record["cache_hit"] is True
    assert record["request_id"] == "t1"


def test_early_return_paths_emit_exactly_once():
    from app.pipeline.result import PipelineResult

    for route in ("distress", "adversarial", "timeout", "error", "casual"):
        _, emit = _run_execute(PipelineResult(trace_id="t", route_decision=route))
        assert emit.call_count == 1, route


def test_result_assembly_no_longer_emits():
    import inspect

    from app.pipeline.stages import glue_stages

    assert "emit_answer_outcome" not in inspect.getsource(glue_stages)


def test_wrapper_failure_never_breaks_response():
    from unittest.mock import patch

    from app.pipeline.result import PipelineResult

    res = PipelineResult(trace_id="t", route_decision="casual")
    with patch("app.answer_outcome.build_answer_outcome", side_effect=RuntimeError("boom")):
        out, _ = _run_execute(res)
    assert out is res
