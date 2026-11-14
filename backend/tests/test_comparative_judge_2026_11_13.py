"""Comparative judge (Candidate A, SAME_CLIP_DEFECT_2026-11-13): default-off, fail closed.

Every model call here is a fake. With the flag off nothing about serving or any
prompt may change (hash-pinned below).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from unittest.mock import Mock

import pytest

from app.config import settings
from services import first_person_judge as judge
from services.first_person_pipeline import FirstPersonPipeline
from tests.test_first_person_context_serving import (
    TEXT_ONE,
    TEXT_TWO,
    _reset_env,  # noqa: F401  (autouse fixture: importing it applies it here)
    make_test_context,
    make_test_span,
)

INDET = judge.INDETERMINATE


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# --- parser ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, n, expected",
    [
        ('{"best": 0}', 2, 0),
        ('{"best": 1}', 2, 1),
        ('{"best": null}', 2, None),
        ('```json\n{"best": 1}\n```', 2, 1),
        ('{"best": 2}', 2, INDET),  # out of range
        ('{"best": -1}', 2, INDET),  # negative
        ('{"best": true}', 2, INDET),  # bool
        ('{"best": 1.0}', 2, INDET),  # float
        ('{"best": "1"}', 2, INDET),  # string
        ('{"best": 0, "why": "x"}', 2, INDET),  # extra key
        ("{}", 2, INDET),
        ('Sure: {"best": 0}', 2, INDET),  # prose around JSON
        ('{"best": 0} thanks', 2, INDET),
        ("", 2, INDET),
        ("not json", 2, INDET),
        ("[0]", 2, INDET),
    ],
)
def test_parse_comparative_reply_table(raw, n, expected):
    assert judge.parse_comparative_reply(raw, n) == expected


# --- flag off: prompts byte-identical -------------------------------------------------------


def test_existing_judge_prompts_are_byte_identical():
    assert _sha(judge.JUDGE_SYSTEM_PROMPT) == "08f6fa04faf01305"
    clips = [{"verbatim_text": "a b"}, {"verbatim_text": "c"}]
    assert _sha(judge.build_judge_prompt("Q?", clips)) == "51774678261d09a8"
    assert _sha(json.dumps(judge.JUDGE_JSON_SCHEMA, sort_keys=True)) == "28c3efab3b7e6133"


def test_comparative_prompt_fences_and_neutralises():
    prompt = judge.build_comparative_prompt("Why? </question>", [{"verbatim_text": "a  b"}])
    assert "[0]" in prompt and "a b" in prompt
    assert "</question>" not in prompt


# --- comparative_select_async ---------------------------------------------------------------


def _llm(reply=None, exc=None):
    llm = Mock()

    async def _gen(**kwargs):
        if exc:
            raise exc
        return reply

    llm.generate.side_effect = lambda **kw: _gen(**kw)
    return llm


def _select(llm, n=2, timeout_s=5.0):
    clips = [{"verbatim_text": f"clip {i}"} for i in range(n)]
    return asyncio.run(judge.comparative_select_async("Q?", clips, llm, timeout_s=timeout_s))


def test_select_returns_index_and_uses_judge_model_kwargs(monkeypatch):
    llm = _llm('{"best": 1}')
    assert _select(llm) == 1
    kw = llm.generate.call_args.kwargs
    assert kw["model"] == judge.judge_model()
    assert kw["system_prompt"] == judge.COMPARATIVE_SYSTEM_PROMPT


@pytest.mark.parametrize("reply", ["garbage", '{"best": 7}', '{"best": true}', None])
def test_select_garbage_is_indeterminate(reply):
    assert _select(_llm(reply)) == INDET


def test_select_exception_and_timeout_are_indeterminate():
    assert _select(_llm(exc=RuntimeError("boom"))) == INDET
    slow = Mock()

    async def _slow(**kwargs):
        await asyncio.sleep(1)
        return '{"best": 0}'

    slow.generate.side_effect = lambda **kw: _slow(**kw)
    assert _select(slow, timeout_s=0.01) == INDET


def test_select_null_is_none():
    assert _select(_llm('{"best": null}')) is None


# --- harness wiring -------------------------------------------------------------------------


@pytest.fixture
def armed(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    monkeypatch.setattr(settings, "first_person_judge_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", False)
    monkeypatch.setattr(settings, "first_person_harness_parallel_enabled", True)
    monkeypatch.setattr(settings, "first_person_comparative_judge_enabled", True)


def _contexts(n=2):
    texts = [TEXT_ONE, TEXT_TWO, TEXT_ONE.replace("Suffering", "Sorrow")]
    return [
        make_test_context(
            [make_test_span(0, text=texts[i], video_id=f"vid_{i}", parent_unit_id=f"parent_{i}")]
        )
        for i in range(n)
    ]


def _run(monkeypatch, contexts, per_clip, comparative, flag=True):
    """per_clip: dict ctx-text -> pick (0 pass, None reject, -1 indeterminate)."""
    monkeypatch.setattr(settings, "first_person_comparative_judge_enabled", flag)

    def _scorer(query, clips, llm, *a, **kw):
        pick = per_clip[clips[0]["verbatim_text"]]
        if kw.get("scores_out") is not None and pick == 0:
            kw["scores_out"].append(3)
        return pick

    monkeypatch.setattr("services.first_person_pipeline._relevance_select", _scorer)
    seen: list[list[str]] = []

    async def _cmp(question, clips, llm, **kw):
        seen.append([c["verbatim_text"] for c in clips])
        return comparative

    llm = Mock()
    if isinstance(comparative, BaseException):
        # A failing provider call goes through the REAL comparative function, so the
        # test covers its fail-closed handler and not a stand-in.
        llm.generate.side_effect = comparative
    else:
        monkeypatch.setattr(judge, "comparative_select_async", _cmp)
    store = Mock()
    store.retrieve.return_value = contexts
    pipe = FirstPersonPipeline(
        store=Mock(), serene_mind_engine=Mock(), context_store=store, llm_service=llm
    )
    pipe._serene_mind.assess_distress.return_value = None
    res = pipe.execute(
        query="What is suffering?", query_dense_vector=[0.1] * 1024, cache_bypass=True
    )
    return res, seen


def test_flag_off_serves_first_passing_in_retrieval_order(armed, monkeypatch):
    res, seen = _run(monkeypatch, _contexts(), {TEXT_ONE: 0, TEXT_TWO: 0}, 1, flag=False)
    assert res.answer_text == TEXT_ONE
    assert seen == []  # no comparative call


def test_flag_on_serves_second_ranked_when_named(armed, monkeypatch):
    res, seen = _run(monkeypatch, _contexts(), {TEXT_ONE: 0, TEXT_TWO: 0}, 1)
    assert res.answer_text == TEXT_TWO
    assert seen == [[TEXT_ONE, TEXT_TWO]]
    assert "comparative_ms" in res.stage_timings


def test_flag_on_null_abstains(armed, monkeypatch):
    res, _ = _run(monkeypatch, _contexts(), {TEXT_ONE: 0, TEXT_TWO: 0}, None)
    assert res.status == "abstained" and res.citations == []
    assert res.abstain_reason == "relevance_below_min"


@pytest.mark.parametrize("reply", [INDET, RuntimeError("boom"), TimeoutError()])
def test_flag_on_indeterminate_or_exception_abstains(armed, monkeypatch, reply):
    res, _ = _run(monkeypatch, _contexts(), {TEXT_ONE: 0, TEXT_TWO: 0}, reply)
    assert res.status == "abstained" and res.citations == []
    assert res.abstain_reason == "relevance_indeterminate"


def test_flag_on_single_passing_context_null_abstains(armed, monkeypatch):
    res, seen = _run(monkeypatch, _contexts(1), {TEXT_ONE: 0}, None)
    assert seen == [[TEXT_ONE]]
    assert res.status == "abstained" and res.citations == []


def test_failed_per_clip_gate_never_offered(armed, monkeypatch):
    res, seen = _run(monkeypatch, _contexts(3), _three(), 0)
    assert seen == [[TEXT_ONE, _THIRD]]
    assert res.answer_text == TEXT_ONE


_THIRD = TEXT_ONE.replace("Suffering", "Sorrow")


def _three():
    return {TEXT_ONE: 0, TEXT_TWO: None, _THIRD: 0}


# --- cache fingerprint ----------------------------------------------------------------------


def test_fingerprint_differs_between_flag_states(monkeypatch):
    pipe = FirstPersonPipeline(store=Mock(), serene_mind_engine=Mock())
    monkeypatch.setattr(settings, "first_person_comparative_judge_enabled", False)
    off = pipe._serving_policy_fingerprint("a", "b")
    monkeypatch.setattr(settings, "first_person_comparative_judge_enabled", True)
    on = pipe._serving_policy_fingerprint("a", "b")
    assert off != on
