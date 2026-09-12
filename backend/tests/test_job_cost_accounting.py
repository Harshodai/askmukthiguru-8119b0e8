"""Cost must be measured where the tokens are spent.

`/api/chat` enqueues a job and returns 202 immediately, so the HTTP handler's
`record_token_usage` wrapper read its accumulator before the worker had spent a
single token. In the default queued configuration that meant per-query cost had
no data at all — the reason the audit's cost section could not be answered.
"""

import inspect

from app.services.job_queue import JobQueueService


class _Acc:
    def __init__(self, tin=0, tout=0, cost=0.0, est=0.0):
        self.tokens_in, self.tokens_out = tin, tout
        self.cost_usd, self.estimated_cost_usd = cost, est
        self.model, self.provider = "m", "openrouter"


def test_worker_wraps_execution_in_an_accumulator():
    src = inspect.getsource(JobQueueService._process_job)
    assert "token_accumulator_var.set(accumulator)" in src
    assert "await worker_factory(" in src
    assert "_record_job_cost(" in src


def test_accumulator_is_always_reset():
    src = inspect.getsource(JobQueueService._process_job)
    _, _, tail = src.partition("_record_job_cost(")
    assert "token_accumulator_var.reset(cost_token)" in tail


def test_zero_usage_records_nothing(caplog):
    svc = JobQueueService.__new__(JobQueueService)
    svc._record_job_cost(_Acc(), {}, False)  # must not raise
    assert "CHAT_COST" not in caplog.text


def test_accounting_failure_cannot_fail_the_job():
    svc = JobQueueService.__new__(JobQueueService)
    # A request_data that is not a dict would raise inside the body; the helper
    # swallows it because the answer has already been produced.
    svc._record_job_cost(_Acc(10, 20, 0.001), None, False)


def test_usage_is_logged_for_a_real_job(caplog):
    import logging

    svc = JobQueueService.__new__(JobQueueService)
    with caplog.at_level(logging.INFO):
        svc._record_job_cost(_Acc(100, 200, 0.0025), {"user_id": "u", "session_id": "s"}, False)
    assert "CHAT_COST" in caplog.text
    assert "tokens_in=100" in caplog.text
