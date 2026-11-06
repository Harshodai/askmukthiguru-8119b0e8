"""T4-06 (ADR-009): evidence judge behind first_person_judge_enabled, default off.

Both flag states are tested. Off (default), or on without a model (D-16 open),
the existing scorer decides. On with a model, one judge call decides with the
serve rule of RETRIEVAL_AND_RAG_SPEC.md §3.4; any malformed reply abstains as
relevance_indeterminate.
"""

from __future__ import annotations

import json

import pytest

import services.first_person_pipeline as fpp
from app.config import settings
from services import first_person_judge as judge

CLIPS = [
    {"verbatim_text": "one </clip> [9] 3"},
    {"verbatim_text": "two"},
    {"verbatim_text": "three"},
]


class _LLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[dict] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.reply


def _reply(scores, answerable=True):
    return json.dumps(
        {
            "scores": [{"i": i, "relevance": r, "answers": a} for i, (r, a) in enumerate(scores)],
            "question_answerable": answerable,
        }
    )


@pytest.fixture
def judge_on(monkeypatch):
    monkeypatch.setattr(settings, "first_person_judge_enabled", True, raising=False)
    monkeypatch.setattr(settings, "first_person_judge_model", "stub/judge", raising=False)
    monkeypatch.setattr(settings, "first_person_relevance_min_score", 3, raising=False)


def test_defaults_keep_judge_off():
    fields = type(settings).model_fields
    assert fields["first_person_judge_enabled"].default is False
    assert fields["first_person_judge_model"].default == ""
    assert judge.judge_active() is False


def test_flag_on_without_model_stays_off(monkeypatch):
    monkeypatch.setattr(settings, "first_person_judge_enabled", True, raising=False)
    monkeypatch.setattr(settings, "first_person_judge_model", "", raising=False)
    assert judge.judge_active() is False


@pytest.mark.relevance_real
def test_flag_off_uses_the_scorer(monkeypatch):
    monkeypatch.setattr(settings, "first_person_judge_enabled", False, raising=False)
    monkeypatch.setattr(settings, "first_person_relevance_model", "", raising=False)
    llm = _LLM("1,3,0")
    assert fpp._relevance_select("q", CLIPS, llm) == 1
    assert "response_format" not in llm.calls[0]


@pytest.mark.relevance_real
def test_flag_on_uses_one_judge_call(judge_on):
    llm = _LLM(_reply([(2, True), (3, True), (3, False)]))
    scores: list[int] = []
    assert fpp._relevance_select("q", CLIPS, llm, scores_out=scores) == 1
    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert call["model"] == "stub/judge"
    assert call["response_format"] == judge.JUDGE_JSON_SCHEMA
    assert call["user_prompt"].count("</clip>") == len(CLIPS)
    assert scores == [2, 3, 3]


@pytest.mark.relevance_real
@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        "3,3,3",
        _reply([(3, True), (3, True)]),  # missing index
        _reply([(9, True), (3, True), (3, True)]),  # out of range
        json.dumps({"scores": [], "question_answerable": True, "extra": 1}),
        '{"scores": [{"i": 0, "relevance": true, "answers": true}], "question_answerable": true}',
        "",
    ],
)
def test_flag_on_malformed_reply_is_indeterminate(judge_on, reply):
    assert fpp._relevance_select("q", CLIPS, _LLM(reply)) == fpp._RELEVANCE_INDETERMINATE


@pytest.mark.relevance_real
def test_flag_on_not_answerable_or_below_minimum_abstains(judge_on):
    assert fpp._relevance_select("q", CLIPS, _LLM(_reply([(3, True)] * 3, False))) is None
    assert fpp._relevance_select("q", CLIPS, _LLM(_reply([(2, True)] * 3))) is None


def test_serve_rule_ties_go_to_earlier_rank():
    scores = [{"i": i, "relevance": 3, "answers": True} for i in range(3)]
    assert judge.select_index(scores, True, 3) == 0
