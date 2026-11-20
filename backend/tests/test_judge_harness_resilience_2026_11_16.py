"""U1 (2026-11-16): per-clip judge retry, indeterminate-is-not-a-barrier, bounded concurrency.

The judge logic is real; only the LLM is a fake.
"""

from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import Mock

import pytest

from app.config import settings
from services import first_person_judge as judge
from services import first_person_pipeline as fpp
from services.first_person_pipeline import FirstPersonPipeline
from tests.test_first_person_context_serving import (
    TEXT_ONE,
    TEXT_TWO,
    _reset_env,  # noqa: F401  (autouse fixture: importing it applies it here)
    make_test_context,
    make_test_span,
)

INDET = judge.INDETERMINATE
_REAL_RELEVANCE_SELECT = fpp._relevance_select  # captured at import, before conftest stubs it


def _reply(relevance: int, answers: bool = True) -> str:
    return json.dumps(
        {
            "scores": [{"i": 0, "relevance": relevance, "answers": answers}],
            "question_answerable": answers,
        }
    )


PASS = _reply(3)
FAIL = _reply(0, answers=False)


def _fake_llm(handler):
    """handler(user_prompt, call_no) -> reply str, or raises. Sync or async."""
    llm = Mock()
    llm.calls = 0

    async def _gen(**kw):
        llm.calls += 1
        res = handler(kw["user_prompt"], llm.calls)
        if asyncio.iscoroutine(res):
            res = await res
        return res

    llm.generate.side_effect = lambda **kw: _gen(**kw)
    return llm


def _select(llm, timeout_s=5.0):
    return asyncio.run(
        judge.judge_select_async(
            "What is suffering?", [{"verbatim_text": "c"}], llm, minimum=3, timeout_s=timeout_s
        )
    )


# --- retry ----------------------------------------------------------------------------------


def test_retry_succeeds_on_second_try_after_exception():
    def h(_p, n):
        if n == 1:
            raise RuntimeError("provider blip")
        return PASS

    llm = _fake_llm(h)
    assert _select(llm) == 0
    assert llm.calls == 2


def test_retry_succeeds_after_unparseable_reply():
    llm = _fake_llm(lambda _p, n: "not json" if n == 1 else PASS)
    assert _select(llm) == 0
    assert llm.calls == 2


def test_two_failures_are_indeterminate_and_only_one_retry():
    llm = _fake_llm(lambda _p, n: (_ for _ in ()).throw(RuntimeError("down")))
    assert _select(llm) == INDET
    assert llm.calls == 2


def test_retry_never_exceeds_total_budget():
    async def slow(_p, _n):
        await asyncio.sleep(5)
        return PASS

    llm = _fake_llm(slow)
    loop = asyncio.new_event_loop()
    t0 = loop.time()
    out = loop.run_until_complete(
        judge.judge_select_async(
            "q", [{"verbatim_text": "c"}], llm, minimum=3, timeout_s=0.3
        )
    )
    elapsed = loop.time() - t0
    loop.close()
    assert out == INDET
    assert elapsed < 0.6  # one budget, not two


# --- harness ---------------------------------------------------------------------------------


@pytest.fixture
def armed(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    monkeypatch.setattr(settings, "first_person_judge_enabled", True, raising=False)
    monkeypatch.setattr(settings, "first_person_judge_model", "stub/judge", raising=False)
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", True)
    monkeypatch.setattr(settings, "first_person_harness_parallel_enabled", True)
    monkeypatch.setattr(settings, "first_person_comparative_judge_enabled", False)
    # conftest stubs the scorer for the whole suite; these tests need the real judge path.
    monkeypatch.setattr(fpp, "_relevance_select", _REAL_RELEVANCE_SELECT)


_TEXTS = [TEXT_ONE, TEXT_TWO, TEXT_ONE.replace("Suffering", "Sorrow")]


def _contexts(n):
    return [
        make_test_context(
            [make_test_span(0, text=_TEXTS[i % 3], video_id=f"v{i}", parent_unit_id=f"p{i}")]
        )
        for i in range(n)
    ]


def _run(contexts, per_text):
    """per_text: ctx text -> reply str, or an Exception to raise on every attempt."""

    def h(prompt, _n):
        for text, reply in per_text.items():
            if text in prompt:
                if isinstance(reply, BaseException):
                    raise reply
                return reply
        raise AssertionError("unexpected prompt")

    llm = _fake_llm(h)
    store = Mock()
    store.retrieve.return_value = contexts
    pipe = FirstPersonPipeline(
        store=Mock(), serene_mind_engine=Mock(), context_store=store, llm_service=llm
    )
    pipe._serene_mind.assess_distress.return_value = None
    return pipe.execute(
        query="What is suffering?", query_dense_vector=[0.1] * 1024, cache_bypass=True
    )


def test_indeterminate_at_index0_does_not_block_a_pass_at_index1(armed, caplog):
    caplog.set_level(logging.INFO)
    res = _run(_contexts(2), {TEXT_ONE: RuntimeError("boom"), TEXT_TWO: PASS})
    assert res.status != "abstained"
    assert res.answer_text == TEXT_TWO
    # one summary line: 1 passed, 0 failed, 1 indeterminate, retried=1 (ctx 0 retried once)
    assert any(
        "judge summary: passed=1 failed=0 indeterminate=1 retried=1" in r.getMessage()
        for r in caplog.records
    )


def test_all_indeterminate_abstains_relevance_indeterminate(armed):
    res = _run(_contexts(2), {TEXT_ONE: RuntimeError("x"), TEXT_TWO: "garbage"})
    assert res.status == "abstained" and res.citations == []
    assert res.abstain_reason == "relevance_indeterminate"


def test_all_fail_abstains(armed):
    res = _run(_contexts(2), {TEXT_ONE: FAIL, TEXT_TWO: FAIL})
    assert res.status == "abstained" and res.citations == []
    assert res.abstain_reason != "relevance_indeterminate"  # a clean fail is not an outage


def test_failed_plus_indeterminate_still_abstains_fail_closed(armed):
    res = _run(_contexts(2), {TEXT_ONE: FAIL, TEXT_TWO: RuntimeError("x")})
    assert res.status == "abstained" and res.citations == []


def test_concurrency_never_exceeds_four(armed, monkeypatch):
    state = {"now": 0, "peak": 0}

    async def h(prompt, _n):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.05)
        state["now"] -= 1
        return FAIL

    monkeypatch.setattr(settings, "first_person_context_max_spans", 16, raising=False)
    llm = _fake_llm(h)
    store = Mock()
    store.retrieve.return_value = _contexts(3) * 3  # 9 contexts, 3 distinct texts
    pipe = FirstPersonPipeline(
        store=Mock(), serene_mind_engine=Mock(), context_store=store, llm_service=llm
    )
    pipe._serene_mind.assess_distress.return_value = None
    pipe.execute(query="What is suffering?", query_dense_vector=[0.1] * 1024, cache_bypass=True)
    assert llm.calls >= 5  # enough to have exceeded concurrency limit if unbounded
    # d084cdb3 lowered the cap 4 -> 2; the invariant this test names is "never above four".
    assert state["peak"] <= fpp._HARNESS_JUDGE_CONCURRENCY <= 4
