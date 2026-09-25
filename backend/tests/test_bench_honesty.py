"""Proves the 2026-09-24 bench-honesty fix: timeouts, 429s, 5xxs and empty
answers count as SYSTEM ERRORS and are excluded from quality metrics.

Root cause this guards: bench_e2e_clean_20260919.json had 1,096 ReadTimeouts +
91 ReadErrors and 1,187/1,226 empty answers, yet reported system_error_rate=0
-- because `system_error` was computed only from grounding_state/intent/
route_decision, fields a transport failure never has. No live backend is used
here (httpx.MockTransport / monkeypatch only), per the task's own constraint.
"""

from __future__ import annotations

import json

import httpx
import pytest

from evaluation import bench
from evaluation.bench import (
    _ask_with_retry,
    _norm,
    aggregate,
    apply_validity_threshold,
    score_row,
)


def _item(id_: str = "t-001", **overrides) -> dict:
    base = _norm(id_, "beautiful_state", "golden_qa_bank", "What is the Beautiful State?")
    base.update(overrides)
    return base


def _http_error(status: int, retry_after: str | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://fake/api/chat")
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(status, request=request, headers=headers)
    return httpx.HTTPStatusError(f"{status}", request=request, response=response)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Timeout / 429 / empty answer each classify correctly and count as errors
# ═══════════════════════════════════════════════════════════════════════════


def test_timeout_is_classified_and_counted_as_system_error():
    item = _item()
    raw = {"_err": "ReadTimeout: "}  # exactly what run_e2e records for httpx.ReadTimeout
    row = score_row(item, raw, latency_s=180.0, mode="anonymous", qdrant_client=None, voice_profile=None)

    assert row.error_class == "timeout"
    assert row.system_error is True

    report = aggregate([row], mode="e2e:anonymous", sources=["golden_qa_bank"], started_at="t0")
    assert report.n_error == 1
    assert report.n_success == 0
    assert report.error_rate == 1.0
    assert report.system_error_rate == 1.0
    assert report.error_breakdown == {"timeout": 1}


def test_http_429_is_classified_and_counted_as_system_error():
    item = _item()
    raw = {"_http": 429, "_body": "rate limited"}
    row = score_row(item, raw, latency_s=0.5, mode="anonymous", qdrant_client=None, voice_profile=None)

    assert row.error_class == "http_429"
    assert row.system_error is True

    report = aggregate([row], mode="e2e:anonymous", sources=["golden_qa_bank"], started_at="t0")
    assert report.error_breakdown == {"http_429": 1}
    assert report.error_rate == 1.0


def test_http_5xx_is_classified_as_system_error():
    item = _item()
    raw = {"_http": 503, "_body": "bad gateway"}
    row = score_row(item, raw, latency_s=0.5, mode="anonymous", qdrant_client=None, voice_profile=None)
    assert row.error_class == "http_5xx"
    assert row.system_error is True


def test_read_error_is_classified_as_system_error():
    item = _item()
    raw = {"_err": "ReadError: "}
    row = score_row(item, raw, latency_s=1.0, mode="anonymous", qdrant_client=None, voice_profile=None)
    assert row.error_class == "read_error"
    assert row.system_error is True


def test_empty_answer_is_classified_and_counted_as_system_error():
    """A real HTTP 200 with a blank/whitespace response body -- the case that
    is NOT an exception and NOT a non-2xx status, so it needs its own check."""
    item = _item()
    raw = {"response": "   ", "grounding_state": "grounded", "citations": []}
    row = score_row(item, raw, latency_s=2.0, mode="anonymous", qdrant_client=None, voice_profile=None)

    assert row.error_class == "empty_answer"
    assert row.system_error is True

    report = aggregate([row], mode="e2e:anonymous", sources=["golden_qa_bank"], started_at="t0")
    assert report.error_breakdown == {"empty_answer": 1}


def test_missing_response_field_is_classified_as_missing_fields():
    item = _item()
    raw = {"grounding_state": "grounded"}  # malformed 200: no "response" key at all
    row = score_row(item, raw, latency_s=1.0, mode="anonymous", qdrant_client=None, voice_profile=None)
    assert row.error_class == "missing_fields"
    assert row.system_error is True


def test_pipeline_wedge_still_classified_as_system_error_not_transport():
    """The pre-existing signal (grounding_state=system_error) must still work
    and get its own class, distinct from a transport failure."""
    item = _item()
    raw = {
        "response": "The guru is unable to answer this question right now.",
        "grounding_state": "system_error",
        "citations": [],
    }
    row = score_row(item, raw, latency_s=0.011, mode="anonymous", qdrant_client=None, voice_profile=None)
    assert row.system_error is True
    assert row.error_class == "pipeline_error"


def test_real_success_has_no_error_class():
    item = _item()
    raw = {
        "response": "The Beautiful State is an inner state of calm and connection.",
        "grounding_state": "grounded",
        "citations": [],
    }
    row = score_row(item, raw, latency_s=1.0, mode="anonymous", qdrant_client=None, voice_profile=None)
    assert row.error_class is None
    assert row.system_error is False


# ═══════════════════════════════════════════════════════════════════════════
# 2. A run above the error-rate threshold is marked INVALID
# ═══════════════════════════════════════════════════════════════════════════


def test_run_above_threshold_is_marked_invalid():
    item = _item()
    good = {"response": "The Beautiful State is calm and connection.", "grounding_state": "grounded"}
    timeout_raw = {"_err": "ReadTimeout: "}
    rows = [
        score_row(item, good, 1.0, "anonymous", None, None),
        score_row(item, timeout_raw, 180.0, "anonymous", None, None),
    ]
    report = aggregate(rows, mode="e2e:anonymous", sources=["golden_qa_bank"], started_at="t0")
    assert report.error_rate == 0.5  # 1/2 -- far above any sane default threshold

    report = apply_validity_threshold(report, max_error_rate=0.01)
    assert report.valid is False
    assert "exceeds max_error_rate" in report.invalid_reason
    # This is exactly what main() uses to decide the process exit code.
    exit_code = 0 if (report.valid and report.gates_passed) else 1
    assert exit_code == 1


def test_run_below_threshold_stays_valid():
    item = _item()
    good = {"response": "The Beautiful State is calm and connection.", "grounding_state": "grounded"}
    rows = [score_row(item, good, 1.0, "anonymous", None, None) for _ in range(99)]
    rows.append(score_row(item, {"_err": "ReadTimeout: "}, 180.0, "anonymous", None, None))
    report = aggregate(rows, mode="e2e:anonymous", sources=["golden_qa_bank"], started_at="t0")
    assert report.error_rate == 0.01

    report = apply_validity_threshold(report, max_error_rate=0.02)
    assert report.valid is True
    assert report.invalid_reason is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. Backoff retries a 429 then succeeds
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_retry_recovers_from_a_single_429():
    calls = {"n": 0}

    async def ask_fn() -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(429, retry_after="0")
        return {"response": "recovered", "grounding_state": "grounded"}

    result = await _ask_with_retry(ask_fn, max_attempts=3)
    assert result == {"response": "recovered", "grounding_state": "grounded"}
    assert calls["n"] == 2, "must have retried exactly once after the 429"


@pytest.mark.asyncio
async def test_retry_gives_up_after_max_attempts_and_returns_err_dict():
    async def ask_fn() -> dict:
        raise _http_error(503)

    result = await _ask_with_retry(ask_fn, max_attempts=2)
    assert "_err" in result
    assert "503" in result["_err"] or "HTTPStatusError" in result["_err"]


@pytest.mark.asyncio
async def test_non_retryable_error_is_not_retried():
    """A 400 (bad request) is a real client error -- retrying it just wastes
    time before the same inevitable failure."""
    calls = {"n": 0}

    async def ask_fn() -> dict:
        calls["n"] += 1
        raise _http_error(400)

    result = await _ask_with_retry(ask_fn, max_attempts=5)
    assert calls["n"] == 1, "a 400 must not be retried"
    assert "_err" in result


# ═══════════════════════════════════════════════════════════════════════════
# 4. Resume skips completed ids
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_resume_skips_completed_ids(tmp_path, monkeypatch):
    items = [_item("q1", question="Q1?"), _item("q2", question="Q2?")]
    monkeypatch.setattr(bench, "load_questions", lambda sources, sample: items)

    out_path = tmp_path / "bench_e2e.json"
    checkpoint_path = tmp_path / "bench_e2e.checkpoint.jsonl"
    already_done = score_row(
        items[0], {"response": "already done", "grounding_state": "grounded"}, 1.0, "anonymous", None, None
    )
    checkpoint_path.write_text(already_done.model_dump_json() + "\n")

    asked: list[str] = []

    async def fake_ask_anonymous(client, endpoint, question, timeout=None):
        asked.append(question)
        return {"response": "fresh answer", "grounding_state": "grounded"}

    monkeypatch.setattr(bench, "_ask_anonymous", fake_ask_anonymous)

    report = await bench.run_e2e(
        "http://fake",
        "anonymous",
        ["golden_qa_bank"],
        None,
        0.0,
        out_path,
        concurrency=2,
        max_attempts=1,
        resume=True,
        checkpoint_path=checkpoint_path,
    )

    assert asked == ["Q2?"], "q1 was already checkpointed -- only q2 should have been asked"
    assert report.total_questions == 2
    assert {r.id for r in report.rows} == {"q1", "q2"}


@pytest.mark.asyncio
async def test_without_resume_checkpoint_is_reset(tmp_path, monkeypatch):
    """Without --resume, a stale checkpoint must not silently skip questions."""
    items = [_item("q1", question="Q1?")]
    monkeypatch.setattr(bench, "load_questions", lambda sources, sample: items)

    out_path = tmp_path / "bench_e2e.json"
    checkpoint_path = tmp_path / "bench_e2e.checkpoint.jsonl"
    stale = score_row(
        items[0], {"response": "stale", "grounding_state": "grounded"}, 1.0, "anonymous", None, None
    )
    checkpoint_path.write_text(stale.model_dump_json() + "\n")

    asked: list[str] = []

    async def fake_ask_anonymous(client, endpoint, question, timeout=None):
        asked.append(question)
        return {"response": "fresh answer", "grounding_state": "grounded"}

    monkeypatch.setattr(bench, "_ask_anonymous", fake_ask_anonymous)

    await bench.run_e2e(
        "http://fake",
        "anonymous",
        ["golden_qa_bank"],
        None,
        0.0,
        out_path,
        concurrency=1,
        max_attempts=1,
        resume=False,
        checkpoint_path=checkpoint_path,
    )
    assert asked == ["Q1?"], "without --resume, q1 must be re-asked, not skipped"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Quality metrics exclude errored items
# ═══════════════════════════════════════════════════════════════════════════


def test_quality_metrics_exclude_errored_rows():
    """This is the exact live defect: an errored row with no must_mention
    terms defaulted to coverage=1.0 and refused=False, silently inflating
    must_mention_coverage and deflating refusal_rate."""
    item_no_terms = _item("t-err", must_mention=[])
    timeout_row = score_row(
        item_no_terms, {"_err": "ReadTimeout: "}, 180.0, "anonymous", None, None
    )
    item_covered = _item("t-ok", must_mention=["beautiful state"])
    good_row = score_row(
        item_covered,
        {"response": "The Beautiful State is calm.", "grounding_state": "grounded"},
        1.0,
        "anonymous",
        None,
        None,
    )

    report = aggregate(
        [timeout_row, good_row], mode="e2e:anonymous", sources=["golden_qa_bank"], started_at="t0"
    )

    assert report.n_success == 1
    assert report.n_error == 1
    # Coverage must be computed ONLY over the one real success (1.0), not
    # averaged with the timeout row's spurious default coverage=1.0-from-empty
    # -must-mention -- in this case both are 1.0 so use a distinguishing case
    # below; here we assert the errored row never entered the denominator.
    assert report.must_mention_coverage_all == 1.0

    # A must_mention miss on the errored row's twin (had it "succeeded") would
    # change this number; prove the denominator is n_success (1), not n (2),
    # by checking refusal_rate is computed the same way.
    assert report.category_breakdown["beautiful_state"]["count"] == 1, (
        "the errored row must not appear in category_breakdown"
    )


def test_quality_metrics_denominator_is_success_only_not_all_rows():
    item = _item(must_mention=["nonexistent phrase that will never match"])
    wrong_answer = score_row(
        item,
        {"response": "totally different text", "grounding_state": "grounded"},
        1.0,
        "anonymous",
        None,
        None,
    )
    error_rows = [
        score_row(item, {"_err": "ReadTimeout: "}, 180.0, "anonymous", None, None) for _ in range(9)
    ]
    report = aggregate(
        [wrong_answer, *error_rows], mode="e2e:anonymous", sources=["golden_qa_bank"], started_at="t0"
    )
    assert report.n_success == 1
    assert report.n_error == 9
    # coverage=0.0 for the single real (wrong) answer -- if error rows leaked
    # into the denominator with their spurious coverage=1.0 default, this
    # would read close to 0.9 instead.
    assert report.must_mention_coverage_all == 0.0
    assert report.refusal_rate == 0.0  # the one real answer did not refuse


# ═══════════════════════════════════════════════════════════════════════════
# Offline rescoring of a pre-fix report (no live backend, pure re-aggregation)
# ═══════════════════════════════════════════════════════════════════════════


def test_rescore_report_recovers_true_error_rate(tmp_path):
    old_style_rows = [
        {
            "id": "t-1",
            "category": "cat",
            "source": "golden_qa_bank",
            "mode": "anonymous",
            "question": "Q?",
            "error": "ReadTimeout: ",
            "answer": "",
            "system_error": False,  # what the OLD (broken) aggregation recorded
        },
        {
            "id": "t-2",
            "category": "cat",
            "source": "golden_qa_bank",
            "mode": "anonymous",
            "question": "Q?",
            "answer": "a real grounded answer",
            "system_error": False,
        },
    ]
    old_report = {
        "mode": "e2e:anonymous",
        "sources": ["golden_qa_bank"],
        "total_questions": 2,
        "completed": 2,
        "started_at": "t0",
        "system_error_rate": 0.0,  # the exact lie this fix corrects
        "rows": old_style_rows,
    }
    path = tmp_path / "bench_e2e_old.json"
    path.write_text(json.dumps(old_report))

    rescored = bench.rescore_report(path)
    assert rescored.n_error == 1
    assert rescored.n_success == 1
    assert rescored.error_rate == 0.5
    assert rescored.system_error_rate == 0.5
    assert rescored.error_breakdown == {"timeout": 1}


if __name__ == "__main__":
    import asyncio as _asyncio

    test_timeout_is_classified_and_counted_as_system_error()
    test_http_429_is_classified_and_counted_as_system_error()
    test_http_5xx_is_classified_as_system_error()
    test_read_error_is_classified_as_system_error()
    test_empty_answer_is_classified_and_counted_as_system_error()
    test_missing_response_field_is_classified_as_missing_fields()
    test_pipeline_wedge_still_classified_as_system_error_not_transport()
    test_real_success_has_no_error_class()
    test_run_above_threshold_is_marked_invalid()
    test_run_below_threshold_stays_valid()
    _asyncio.run(test_retry_recovers_from_a_single_429())
    _asyncio.run(test_retry_gives_up_after_max_attempts_and_returns_err_dict())
    _asyncio.run(test_non_retryable_error_is_not_retried())
    test_quality_metrics_exclude_errored_rows()
    test_quality_metrics_denominator_is_success_only_not_all_rows()
    print("bench honesty self-check OK")


def test_read_timeout_is_not_retried_but_connect_timeout_is():
    """A ReadTimeout means the server used the whole budget; retrying it only
    tripled wall time (547s rows, 2026-09-25). Connect-level failures stay retryable."""
    import httpx

    from evaluation.bench import _is_retryable_transport_error

    assert _is_retryable_transport_error(httpx.ReadTimeout("slow")) is False
    assert _is_retryable_transport_error(httpx.ConnectTimeout("net")) is True
    assert _is_retryable_transport_error(httpx.ConnectError("net")) is True
