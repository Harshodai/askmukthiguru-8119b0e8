"""T2-03: answer_outcome record and metrics."""

import json

from app.answer_outcome import (
    build_answer_outcome,
    compute_useful_answer,
    emit_answer_outcome,
    record_useful_answer_signal,
)
from app.metrics import ANSWER_OUTCOME_TOTAL, INTEGRITY_BREACH_TOTAL, USEFUL_ANSWER_TOTAL
from services.cost_tracker import TokenAccumulator

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
    r = _rec(
        stage_latencies_ms={"retrieval": 12.5, "rerank": 35.0},
        llm_calls=[
            {
                "prompt_id": "answerability@v1",
                "model": "deepseek/deepseek-chat",
                "tokens_in": 120,
                "tokens_out": 25,
                "cost_usd": 0.00015,
            }
        ],
    )
    blob = json.dumps(r)
    assert SEEKER not in blob and ANSWER not in blob
    for k in ("user_id", "session_id", "message", "answer", "final_answer"):
        assert k not in r
    assert r["stage_latencies_ms"]["retrieval"] == 12.5
    assert len(r["llm_calls"]) == 1
    assert r["total_tokens_in"] == 120
    assert r["total_tokens_out"] == 25
    assert r["total_cost_usd"] == 0.00015


def test_token_accumulator_records_calls():
    acc = TokenAccumulator()
    acc.record_call(
        prompt_id="scorer@v2",
        model="deepseek/deepseek-chat",
        tokens_in=200,
        tokens_out=50,
        cost_usd=0.0003,
    )
    assert len(acc.llm_calls) == 1
    call = acc.llm_calls[0]
    assert call["prompt_id"] == "scorer@v2"
    assert call["tokens_in"] == 200
    assert call["tokens_out"] == 50
    assert call["cost_usd"] == 0.0003


def test_compute_useful_answer():
    # useful_answer = served AND (helpful OR played >= 20 s OR saved) AND NOT reported
    assert compute_useful_answer(outcome="served", helpful=True) == (True, "helpful")
    assert compute_useful_answer(outcome="served", played_seconds=22.5) == (True, "played_20s")
    assert compute_useful_answer(outcome="served", saved=True) == (True, "saved")

    # Not served
    assert compute_useful_answer(outcome="abstained", helpful=True) == (False, "not_served")
    assert compute_useful_answer(outcome="crisis", played_seconds=30) == (False, "not_served")

    # Reported cancels usefulness
    assert compute_useful_answer(outcome="served", helpful=True, reported=True) == (
        False,
        "reported",
    )
    assert compute_useful_answer(outcome="served", played_seconds=30, reported=True) == (
        False,
        "reported",
    )

    # Unconfirmed
    assert compute_useful_answer(outcome="served", helpful=False, played_seconds=5) == (
        False,
        "unconfirmed",
    )


def test_record_useful_answer_signal():
    before = USEFUL_ANSWER_TOTAL.labels(lane="teaching", signal="helpful")._value.get()
    record_useful_answer_signal(lane="teaching", signal="helpful")
    assert USEFUL_ANSWER_TOTAL.labels(lane="teaching", signal="helpful")._value.get() == before + 1


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


def test_coordinator_passes_stage_latencies_and_llm_calls():
    from app.pipeline.result import PipelineResult
    from services.cost_tracker import TokenAccumulator, token_accumulator_var

    acc = TokenAccumulator()
    acc.record_call(prompt_id="test@v1", model="m", tokens_in=10, tokens_out=5, cost_usd=0.00001)
    tok = token_accumulator_var.set(acc)
    try:
        res = PipelineResult(
            trace_id="t_lat",
            route_decision="first_person_bridge",
            route_metadata={"stage_timings": {"retrieval_ms": 15.0}},
        )
        _, emit = _run_execute(res)
        assert emit.call_count == 1
        rec = emit.call_args.args[0]
        assert rec["stage_latencies_ms"] == {"retrieval_ms": 15.0}
        assert len(rec["llm_calls"]) == 1
        assert rec["llm_calls"][0]["prompt_id"] == "test@v1"
    finally:
        token_accumulator_var.reset(tok)


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
