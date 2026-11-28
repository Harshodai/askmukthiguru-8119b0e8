"""2026-11-28: the judge retry must re-ask the model, and a failed judge must say why.

Live evidence ('Is it okay to cry?'): four `verify` calls of ~1-1.6 s, then a fifth of 30 ms
with cost 0 and ESTIMATED tokens, and the turn abstained `relevance_indeterminate`. Every
OpenRouter call sends `X-OpenRouter-Cache: true`; a cache HIT is 30 ms, zero billed usage
(the service then estimates tokens) and returns the first body byte for byte. A judge
reply that failed the strict parser was therefore replayed by the "retry". The retry now
sends `X-OpenRouter-Cache-Clear: true`. Policy is unchanged: a second failure is still
INDETERMINATE and abstains.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock

import pytest

from app.config import settings
from app.turn_trace import TurnTrace, turn_trace_var
from services import first_person_judge as judge
from services import first_person_pipeline as fpp
from services.openrouter_service import (
    OpenRouterService,
    ProviderConnectionError,
    ProviderRefusalError,
)

# Imported at module level: _REAL_RELEVANCE_SELECT is captured before conftest stubs the scorer.
from tests.test_first_person_context_serving import (  # noqa: F401
    TEXT_ONE,
    TEXT_TWO,
    _reset_env,  # autouse fixture
)
from tests.test_judge_harness_resilience_2026_11_16 import (
    _REAL_RELEVANCE_SELECT,
    _contexts,
    _run,
)

PASS = json.dumps(
    {"scores": [{"i": 0, "relevance": 3, "answers": True}], "question_answerable": True}
)


def _llm(replies):
    """replies: list of str or BaseException, one per call. Records each call's kwargs."""
    llm = Mock()
    llm.kwargs = []

    async def _gen(**kw):
        llm.kwargs.append(kw)
        r = replies[min(len(llm.kwargs), len(replies)) - 1]
        if isinstance(r, BaseException):
            raise r
        return r

    llm.generate.side_effect = lambda **kw: _gen(**kw)
    return llm


def _select(llm):
    return asyncio.run(
        judge.judge_select_async("q", [{"verbatim_text": "c"}], llm, minimum=3, timeout_s=5.0)
    )


def _reasons(llm):
    log: list[str] = []
    token = judge.JUDGE_FAIL_LOG.set(log)
    try:
        out = _select(llm)
    finally:
        judge.JUDGE_FAIL_LOG.reset(token)
    return out, log


# --- retry bypasses OpenRouter's response cache ---------------------------------------------


def test_retry_asks_provider_to_refresh_cache_first_attempt_does_not():
    llm = _llm(["not json", PASS])
    assert _select(llm) == 0
    assert "refresh_response_cache" not in llm.kwargs[0]
    assert llm.kwargs[1]["refresh_response_cache"] is True


def test_retry_that_fails_again_is_still_indeterminate():
    llm = _llm(["not json", "still not json"])
    assert _select(llm) == judge.INDETERMINATE
    assert len(llm.kwargs) == 2


@pytest.mark.asyncio
async def test_openrouter_sends_cache_clear_only_when_asked(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-mock-key")
    seen: list[dict] = []

    class Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [{"message": {"content": "x"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

    class Client:
        async def post(self, url, json=None, headers=None, **kw):
            seen.append(dict(headers or {}))
            return Resp()

    async def get_client(self):
        return Client()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", get_client)
    svc = OpenRouterService()
    await svc.generate("s", "u")
    await svc.generate("s", "u", refresh_response_cache=True)
    assert "X-OpenRouter-Cache-Clear" not in seen[0]
    assert seen[1]["X-OpenRouter-Cache"] == "true"
    assert seen[1]["X-OpenRouter-Cache-Clear"] == "true"


# --- bounded reason code ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ("not json", "parse"),
        ("   ", "empty"),
        (RuntimeError("boom"), "provider_error"),
        (TimeoutError(), "timeout"),
        (ProviderConnectionError("down"), "provider_error"),
        (ProviderRefusalError("no"), "refusal"),
    ],
)
def test_failed_judge_records_one_bounded_reason(reply, reason):
    out, log = _reasons(_llm([reply, reply]))
    assert out == judge.INDETERMINATE
    assert log == [reason]  # one entry per indeterminate context, the last attempt's reason


def test_budget_denial_reason():
    from app.openrouter_budget import OpenRouterBudgetExceeded

    out, log = _reasons(_llm([OpenRouterBudgetExceeded("cap")] * 2))
    assert out == judge.INDETERMINATE
    assert log == ["budget"]


def test_successful_retry_records_no_reason():
    out, log = _reasons(_llm(["not json", PASS]))
    assert out == 0 and log == []


def test_reason_codes_are_trace_safe():
    trace = TurnTrace()
    for code in ("parse", "empty", "provider_error", "timeout", "refusal", "budget"):
        trace.note("fp", judge_indeterminate_reason=code)
        assert trace.fp["judge_indeterminate_reason"] == code


# --- the pipeline puts the reason on the trace ------------------------------------------------


def test_pipeline_notes_judge_indeterminate_reason(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    monkeypatch.setattr(settings, "first_person_judge_enabled", True, raising=False)
    monkeypatch.setattr(settings, "first_person_judge_model", "stub/judge", raising=False)
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", True)
    monkeypatch.setattr(settings, "first_person_harness_parallel_enabled", True)
    monkeypatch.setattr(settings, "first_person_comparative_judge_enabled", False)
    monkeypatch.setattr(fpp, "_relevance_select", _REAL_RELEVANCE_SELECT)
    trace = TurnTrace()
    token = turn_trace_var.set(trace)
    try:
        res = _run(_contexts(2), {TEXT_ONE: "garbage", TEXT_TWO: "garbage"})
    finally:
        turn_trace_var.reset(token)
    assert res.abstain_reason == "relevance_indeterminate"
    assert trace.fp["judge_indeterminate"] == 2
    assert trace.fp["judge_indeterminate_reason"] == "parse"
