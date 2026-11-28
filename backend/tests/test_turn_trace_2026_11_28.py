"""Per-turn trace on the `answer_outcome` line (LOG_TURN_TRACE_ENABLED, default off).

Logging only: nothing here may change a gate decision, return value or cache key. With
the flag off the record is exactly the old record and every hook is a no-op.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import turn_trace
from app.answer_outcome import build_answer_outcome, emit_answer_outcome
from app.config import Settings, settings
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.result import PipelineResult
from app.turn_trace import TurnTrace, fp_note, fp_reject, fp_score, turn_trace_var
from services.cost_tracker import TokenAccumulator, token_accumulator_var

_ERRORS = [RuntimeError, ValueError, TypeError, AttributeError, KeyError]


def _base_kwargs(**over):
    kw = dict(
        request_id="t1",
        route_decision="first_person_bridge",
        route_reason="FP declined (status=abstained)",
        grounding_state="abstained",
        citations=[],
        verification={"passed": False, "method": "m", "citations_verified": False},
        cache_hit=False,
        latency_ms=1234,
        model_used=None,
    )
    kw.update(over)
    return kw


# --- defaults are unchanged -----------------------------------------------------------


def test_the_flag_defaults_off():
    assert Settings.model_fields["log_turn_trace_enabled"].default is False


def test_record_without_a_trace_has_no_new_keys():
    record = build_answer_outcome(**_base_kwargs())
    assert not {"turn", "fp", "summary", "job_id", "pid"} & set(record)


def test_log_line_is_still_the_dict_repr_without_a_trace(caplog):
    record = build_answer_outcome(**_base_kwargs())
    with caplog.at_level(logging.INFO, logger="app.answer_outcome"):
        emit_answer_outcome(record, first_person_only=True)
    (line,) = [r for r in caplog.records if r.getMessage().startswith("answer_outcome")]
    assert line.getMessage() == f"answer_outcome {record}"
    assert not hasattr(line, "mg_fields")


def _run_execute(monkeypatch, enabled: bool, inner):
    monkeypatch.setattr(settings, "log_turn_trace_enabled", enabled)
    coord = PipelineCoordinator(MagicMock())
    with (
        patch.object(coord, "_execute_stages", AsyncMock(side_effect=inner)),
        patch("app.answer_outcome.emit_answer_outcome") as emit,
    ):
        out = asyncio.run(
            coord.execute(user_msg="a private question", preferred_lang="en", job_id="job_abc")
        )
    return out, emit


def test_flag_off_leaves_the_var_unset_and_hooks_inert(monkeypatch):
    seen = {}

    async def inner(**kw):
        seen["trace"] = turn_trace_var.get()
        fp_note(n_retrieved=3)  # must be a no-op
        return PipelineResult(trace_id="t", route_decision="casual")

    out, emit = _run_execute(monkeypatch, False, inner)
    assert seen["trace"] is None
    assert "fp" not in emit.call_args.args[0] and "turn" not in emit.call_args.args[0]
    assert out.route_decision == "casual"


# --- the trace on: served, abstained, error exits -------------------------------------


def _served():
    return PipelineResult(
        trace_id="t-served",
        route_decision="first_person_bridge",
        citations=[{"clip_id": "c1"}],
        verification={"passed": True, "method": "m", "citations_verified": True},
        model_used=None,
    )


def _abstained():
    return PipelineResult(
        trace_id="t-abs",
        route_decision="first_person_abstain",
        verification={"passed": True, "method": "m", "citations_verified": False},
    )


def _errored():
    return PipelineResult(trace_id="t-err", route_decision="error")


@pytest.mark.parametrize(
    "make,expected_outcome", [(_served, "served"), (_abstained, "abstained"), (_errored, "error")]
)
def test_every_exit_carries_ids_turn_and_stage_fields(monkeypatch, make, expected_outcome):
    async def inner(**kw):
        fp_note(n_retrieved=4, retrieval_ms=12.3, answerability="yes", abstain_reason="none")
        fp_score(3)
        fp_score(1)
        fp_reject("integrity")
        turn_trace.stage_note("graph", 41.0)
        return make()

    _, emit = _run_execute(monkeypatch, True, inner)
    record = emit.call_args.args[0]
    assert record["outcome"] == expected_outcome
    assert record["job_id"] == "job_abc" and isinstance(record["pid"], int)
    assert record["turn"]["q_len"] == len("a private question")
    assert record["turn"]["lang"] == "en"
    assert record["turn"]["stage_ms"] == {"graph": 41.0}
    assert record["fp"]["n_retrieved"] == 4
    assert record["fp"]["scores"] == [3, 1] and record["fp"]["n_scored"] == 2
    assert record["fp"]["rejected"] == {"integrity": 1}
    assert "summary" in record
    json.dumps(record)  # JSON-serialisable
    assert "private question" not in json.dumps(record)


def test_the_var_is_reset_after_the_turn_even_when_the_pipeline_raises(monkeypatch):
    async def inner(**kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(settings, "log_turn_trace_enabled", True)
    coord = PipelineCoordinator(MagicMock())
    with patch.object(coord, "_execute_stages", AsyncMock(side_effect=inner)):
        with pytest.raises(RuntimeError):
            asyncio.run(coord.execute(user_msg="x", preferred_lang="en"))
    assert turn_trace_var.get() is None


def test_queue_timing_becomes_ms_fields(monkeypatch):
    from app.context import queue_timing_var

    async def inner(**kw):
        coord._note_queue_timing(
            {"admitted_at": 100.0, "claimed_at": 100.5, "ingress_ms": 7.5}, 101.0
        )
        return _served()

    coord = PipelineCoordinator(MagicMock())
    monkeypatch.setattr(settings, "log_turn_trace_enabled", True)
    tok = queue_timing_var.set({})
    try:
        with (
            patch.object(coord, "_execute_stages", AsyncMock(side_effect=inner)),
            patch("app.answer_outcome.emit_answer_outcome") as emit,
        ):
            asyncio.run(coord.execute(user_msg="x", preferred_lang="en"))
    finally:
        queue_timing_var.reset(tok)
    turn = emit.call_args.args[0]["turn"]
    assert turn["queue_wait_ms"] == 500.0
    assert turn["dispatch_ms"] == 500.0
    assert turn["ingress_ms"] == 7.5


# --- gate_that_rejected is a label, derived at build time -----------------------------


def _fp_record(outcome_route="first_person_abstain", **fp):
    trace = TurnTrace()
    trace.note("fp", **fp)
    return trace, outcome_route


def test_gate_label_prefers_a_specific_abstain_reason():
    trace, route = _fp_record(abstain_reason="relevance_below_min")
    rec = build_answer_outcome(**_base_kwargs(route_decision=route), trace=trace)
    assert rec["fp"]["gate_that_rejected"] == "relevance_below_min"


def test_gate_label_uses_the_largest_rejection_bucket_when_nothing_was_scored():
    trace = TurnTrace()
    trace.note("fp", abstain_reason="no_verified_clips")
    for _ in range(3):
        trace.bump("integrity")
    trace.bump("boundary")
    rec = build_answer_outcome(**_base_kwargs(route_decision="first_person_abstain"), trace=trace)
    assert rec["fp"]["gate_that_rejected"] == "integrity"


def test_gate_label_is_min_score_when_every_score_is_below_it():
    trace = TurnTrace()
    trace.note("fp", abstain_reason="none", min_score=2, n_scored=2)
    trace.add_score(1)
    trace.add_score(0)
    rec = build_answer_outcome(**_base_kwargs(route_decision="first_person_abstain"), trace=trace)
    assert rec["fp"]["gate_that_rejected"] == "relevance_min_score"


def test_gate_label_is_none_for_a_served_turn():
    trace = TurnTrace()
    trace.note("fp", abstain_reason="none", n_served=1)
    rec = build_answer_outcome(
        **_base_kwargs(
            citations=[{"clip_id": "c"}],
            verification={"passed": True, "method": "m", "citations_verified": True},
        ),
        trace=trace,
    )
    assert rec["outcome"] == "served" and rec["fp"]["gate_that_rejected"] is None


# --- trace internals: bounded, text-proof, never raising -------------------------------


def test_only_safe_scalars_are_stored():
    trace = TurnTrace()
    trace.note(
        "fp",
        ok_int=1,
        ok_float=1.234,
        ok_bool=True,
        ok_none=None,
        ok_code="relevance_below_min",
        sentence="what is suffering and why",
        mapping={"a": 1},
        nan=math.nan,
        long="x" * 200,
    )
    assert set(trace.fp) == {"ok_int", "ok_float", "ok_bool", "ok_none", "ok_code"}
    assert trace.fp["ok_float"] == 1.23


def test_scores_are_ints_zero_to_three_and_capped():
    trace = TurnTrace()
    for value in (0, 1, 2, 3, 4, -1, "x", None, 2.0):
        trace.add_score(value)
    assert trace.scores == [0, 1, 2, 3, 2]
    for _ in range(40):
        trace.add_score(3)
    assert len(trace.scores) == 12


def test_maps_are_bounded():
    trace = TurnTrace()
    for i in range(200):
        trace.note("fp", **{f"k{i}": i})
        trace.bump(f"gate{i}")
        trace.note_stage(f"stage{i}", 1.0)
    assert len(trace.fp) <= 64 and len(trace.rejected) <= 24 and len(trace.stage_ms) <= 40


@pytest.mark.parametrize("exc", _ERRORS)
def test_no_writer_ever_raises(monkeypatch, exc):
    trace = TurnTrace()

    def boom(*a, **k):
        raise exc("x")

    monkeypatch.setattr(turn_trace, "_clean", boom)
    trace.note("fp", a=1)
    monkeypatch.setattr(trace, "_lock", MagicMock(__enter__=boom, __exit__=boom))
    trace.bump("g")
    trace.add_score(1)
    trace.note_stage("s", 1.0)
    assert trace.snapshot() == {}


@pytest.mark.parametrize("exc", _ERRORS)
def test_a_broken_trace_leaves_the_base_record_intact(exc):
    class _Broken:
        def snapshot(self):
            raise exc("x")

    plain = build_answer_outcome(**_base_kwargs())
    with_broken = build_answer_outcome(**_base_kwargs(), trace=_Broken())
    assert with_broken == plain


def test_helpers_are_noops_without_a_trace():
    assert turn_trace_var.get() is None
    fp_note(a=1)
    fp_reject("x")
    fp_score(1)
    turn_trace.turn_note(a=1)
    turn_trace.stage_note("s", 1.0)


# --- context propagation: tasks and thread hops share the one object --------------------


def test_gather_tasks_and_thread_hops_write_to_the_same_trace():
    trace = TurnTrace()

    async def main():
        tok = turn_trace_var.set(trace)
        try:

            async def task(i):
                fp_score(i % 4)

            await asyncio.gather(*(task(i) for i in range(3)))
            loop = asyncio.get_running_loop()
            ctx = contextvars.copy_context()
            await loop.run_in_executor(None, ctx.run, lambda: fp_note(from_thread=True))
        finally:
            turn_trace_var.reset(tok)

    asyncio.run(main())
    assert sorted(trace.scores) == [0, 1, 2]
    assert trace.fp["from_thread"] is True


# --- per-call LLM records ---------------------------------------------------------------


def test_record_call_defaults_keep_the_old_row():
    acc = TokenAccumulator()
    acc.record_call(prompt_id="p", model="m", tokens_in=1, tokens_out=2, cost_usd=0.1)
    assert set(acc.llm_calls[0]) == {"prompt_id", "model", "tokens_in", "tokens_out", "cost_usd"}


def test_timing_status_and_failed_calls_reach_the_record():
    from services.openrouter_service import OpenRouterService

    acc = TokenAccumulator()
    acc.record_call(
        prompt_id="relevance",
        model="m",
        tokens_in=10,
        tokens_out=2,
        cost_usd=0.001,
        duration_ms=812.34,
        attempts=2,
        limiter_wait_ms=15.0,
        status="ok",
    )
    trace = TurnTrace()
    tok = turn_trace_var.set(trace)
    acc_tok = token_accumulator_var.set(acc)
    try:
        OpenRouterService._record_failed_call(
            operation="answerability",
            model="m",
            status="timeout",
            started=0.0,
            attempts=1,
            limiter_ms=0.0,
        )
    finally:
        token_accumulator_var.reset(acc_tok)
        turn_trace_var.reset(tok)
    rec = build_answer_outcome(**_base_kwargs(), trace=trace, llm_calls=acc.llm_calls)
    ok, failed = rec["llm_calls"]
    assert ok["duration_ms"] == 812.3 and ok["attempts"] == 2 and ok["limiter_wait_ms"] == 15.0
    assert ok["status"] == "ok"
    assert failed["status"] == "timeout" and failed["tokens_in"] == 0 and failed["cost_usd"] == 0
    assert rec["summary"]["llm_calls_n"] == 2
    assert rec["summary"]["retries_sum"] == 1
    assert rec["summary"]["throttle_wait_ms_sum"] == 15.0
    # zero-token rows are neutral in the totals
    assert rec["total_tokens_in"] == 10


def test_failed_calls_are_not_recorded_when_the_trace_is_off():
    from services.openrouter_service import OpenRouterService

    acc = TokenAccumulator()
    tok = token_accumulator_var.set(acc)
    try:
        OpenRouterService._record_failed_call(
            operation="o", model="m", status="error", started=0.0, attempts=1, limiter_ms=0.0
        )
    finally:
        token_accumulator_var.reset(tok)
    assert acc.llm_calls == []


# --- the structured line + formatter -----------------------------------------------------


def test_trace_on_emits_json_message_plus_fields(caplog):
    trace = TurnTrace()
    trace.note("fp", n_retrieved=2)
    record = build_answer_outcome(**_base_kwargs(), trace=trace)
    with caplog.at_level(logging.INFO, logger="app.answer_outcome"):
        emit_answer_outcome(record, first_person_only=True)
    (line,) = [r for r in caplog.records if r.getMessage().startswith("answer_outcome")]
    assert json.loads(line.getMessage().split(" ", 1)[1])["fp"]["n_retrieved"] == 2
    assert line.mg_fields["request_id"] == "t1"


def test_formatter_merges_fields_at_top_level_without_mangling_ids():
    import app.main as main_module

    trace_id = "8f3a4c1d-1234-5678-9012-345678901234"  # long digit runs: phone-regex bait
    record = build_answer_outcome(**_base_kwargs(request_id=trace_id), trace=_trace_with(7))
    log = logging.LogRecord(
        "app.answer_outcome", logging.INFO, __file__, 1, "answer_outcome {}", (), None
    )
    log.mg_fields = record
    out = json.loads(main_module.JSONFormatter(railway_levels=True).format(log))
    assert out["message"] == "answer_outcome"
    assert out["level"] == "info"
    assert out["request_id"] == trace_id
    assert out["outcome"] == "abstained" and out["fp"]["n_retrieved"] == 7
    assert out["latency_ms"] == 1234  # 10-digit-ish numbers stay numbers
    for reserved in ("timestamp", "level", "logger", "message"):
        assert reserved in out


def _trace_with(n):
    trace = TurnTrace()
    trace.note("fp", n_retrieved=n)
    return trace


def test_formatter_without_fields_is_unchanged():
    import app.main as main_module

    log = logging.LogRecord("x", logging.WARNING, __file__, 1, "hello %s", ("world",), None)
    out = json.loads(main_module.JSONFormatter().format(log))
    assert out["message"] == "hello world" and out["level"] == "WARNING"


# --- JOB_RESULT_FETCHED -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_lag_line_is_logged_only_when_enabled_and_completed(monkeypatch, caplog):
    import time

    from app.api import job_routes

    monkeypatch.setattr(job_routes, "resolve_anon_identity", lambda user, session: user)
    monkeypatch.setattr(job_routes, "require_scoped_identity", lambda user: None)
    job = {
        "job_id": "job_x",
        "status": "completed",
        "user_id": "anon:u",
        "created_at": time.time() - 3.0,
        "completed_at": time.time() - 0.5,
        "error": None,
    }
    container = MagicMock()
    container.job_queue.get_job = AsyncMock(return_value=job)
    request = MagicMock()
    request.headers.get.return_value = None
    user = {"id": "anon:u"}

    monkeypatch.setattr(settings, "log_turn_trace_enabled", False)
    with caplog.at_level(logging.INFO, logger="app.api.job_routes"):
        assert await job_routes.get_job("job_x", request, container, user) == job
    assert "JOB_RESULT_FETCHED" not in caplog.text

    monkeypatch.setattr(settings, "log_turn_trace_enabled", True)
    with caplog.at_level(logging.INFO, logger="app.api.job_routes"):
        await job_routes.get_job("job_x", request, container, user)
    (line,) = [r.getMessage() for r in caplog.records if "JOB_RESULT_FETCHED" in r.getMessage()]
    assert "job_id=job_x" in line and "fetch_lag_ms=" in line
    assert "anon" not in line  # no user id


# --- the context-harness path (production serving lane) -----------------------------------


@pytest.mark.asyncio
async def test_harness_path_records_retrieval_answerability_and_rejections(monkeypatch):
    import time

    from services.first_person_pipeline import FirstPersonPipeline

    for name, value in {
        "first_person_context_harness_enabled": True,
        "first_person_context_terminal_enabled": True,
        "first_person_answerability_check_enabled": False,
        "first_person_memgraph_sizing_enabled": False,  # no Memgraph call in a unit test
    }.items():
        monkeypatch.setattr(settings, name, value)

    def build():
        store = MagicMock()
        store.collection = "first_person_v10"
        pipeline = FirstPersonPipeline(
            store=store,
            redis_client=MagicMock(),
            serene_mind_engine=MagicMock(),
            context_store=MagicMock(),
        )
        monkeypatch.setattr(pipeline, "_expand_context_candidates", lambda c, **k: c)
        monkeypatch.setattr(pipeline, "_diversify_candidate_pool", lambda c: c)
        mock_ctx = MagicMock()
        mock_ctx.spans = []
        mock_ctx.hit_span_ids = ()
        mock_ctx.parent.ordered_source_span_ids = ()
        pipeline._context_store.retrieve.return_value = [mock_ctx]
        harness = MagicMock()
        harness._policy.max_context_spans = 3
        harness.decide.return_value = MagicMock(decision="DECLINE")
        pipeline._context_harness = harness
        return pipeline

    async def run(pipeline):
        return await pipeline._serve_from_context_harness(
            query="what is suffering",
            query_dense_vector=[0.1] * 128,
            query_sparse_vector=None,
            teacher_id=None,
            max_clips=3,
            retrieval_query="what is suffering",
            language="en",
            cache_bypass=True,
            request_allow_state="",
            request_block_state="",
            fp_llm_tokens=[],
            _ans_box={},
            start_time=time.monotonic(),
        )

    baseline = await run(build())
    trace = TurnTrace()
    token = turn_trace_var.set(trace)
    try:
        traced = await run(build())
    finally:
        turn_trace_var.reset(token)

    assert (traced.status, traced.abstain_reason) == (baseline.status, baseline.abstain_reason)
    assert trace.fp["n_retrieved"] == 1
    assert trace.fp["answerability"] == "permissive"
    assert trace.fp["abstain_reason"] == traced.abstain_reason
    assert trace.fp["pipeline_status"] == "abstained"
    # decide_* names the harness verdict; abstain_* adds its bounded reason (2026-11-28)
    assert trace.rejected == {"decide_decline": 1, "abstain_other": 1}


# --- the bridge stage hooks -----------------------------------------------------------------

import tests.test_first_person_bridge as _bridge_tests  # noqa: E402

_bridge_gates = _bridge_tests._bridge_gates
fp_pipeline = _bridge_tests.fp_pipeline


@pytest.mark.asyncio
@pytest.mark.parametrize("served", [True, False], ids=["served", "abstained"])
async def test_bridge_records_embed_hyde_and_outcome_fields(fp_pipeline, monkeypatch, served):
    from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage

    monkeypatch.setattr(settings, "first_person_hyde_enabled", False)
    if not served:
        fp_pipeline.execute.return_value = _bridge_tests._fp_result(
            citations=[], status="abstained"
        )
    trace = TurnTrace()
    token = turn_trace_var.set(trace)
    try:
        result = await FirstPersonBridgeStage().run(_bridge_tests._ctx(_bridge_tests._container()))
    finally:
        turn_trace_var.reset(token)
    assert result is not None
    assert trace.fp["hyde_state"] == "off"
    assert trace.fp["embed_calls"] == 1 and trace.fp["embed_ms"] >= 0
    if served:
        assert trace.fp["cached"] is False and "is_direct" in trace.fp
    else:
        assert trace.fp["abstain_cause"] in {"no_evidence", "system_unavailable", "topic_boundary"}


@pytest.mark.asyncio
@pytest.mark.parametrize("with_ingress", [True, False])
async def test_worker_hands_ingress_ms_to_the_pipeline_only_when_present(with_ingress):
    from app.context import queue_timing_var
    from app.services.job_queue import JobQueueService, JobStatus
    from tests.test_job_queue import _MemoryRedis

    redis = _MemoryRedis()
    service = JobQueueService("redis://unused")
    service._redis = redis
    payload = {"message": "x"}
    if with_ingress:
        payload["_ingress_ms"] = 42.5
    redis.hashes["job:job_i:meta"] = {
        "status": JobStatus.QUEUED.value,
        "is_stream": "0",
        "request_data": json.dumps(payload),
        "created_at": "100.0",
        "correlation_id": "c",
    }
    seen: dict = {}

    async def worker_factory(request_data, is_stream, job_id):
        seen.update(queue_timing_var.get())
        return {"ok": True}

    await service._process_job("job_i", worker_factory, worker_id=1)
    assert ("ingress_ms" in seen) is with_ingress
    if with_ingress:
        assert seen["ingress_ms"] == 42.5
