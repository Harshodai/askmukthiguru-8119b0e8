"""T4-06 (ADR-009): evidence judge behind first_person_judge_enabled, default off.

Both flag states are tested. Off (default), or on without a model,
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
    # D-16 (2026-11-07): the model is named; the flag alone keeps the judge off.
    assert fields["first_person_judge_model"].default == "anthropic/claude-haiku-5.5"
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
def test_named_model_gets_the_scorer_call_shape(monkeypatch):
    """D-16 (2026-11-07): the judge model is anthropic/claude-haiku-5.5.

    That model rejects a non-default temperature (CA-1) and reasons before it
    answers, so the judge must send the same shape as the relevance scorer:
    no temperature, max_tokens 2048, operation "verify", reasoning_effort "low".
    """
    monkeypatch.setattr(settings, "first_person_judge_enabled", True, raising=False)
    monkeypatch.setattr(
        settings, "first_person_judge_model", "anthropic/claude-haiku-5.5", raising=False
    )
    monkeypatch.setattr(settings, "first_person_relevance_min_score", 3, raising=False)
    llm = _LLM(_reply([(3, True), (1, False), (0, False)]))
    assert fpp._relevance_select("q", CLIPS, llm) == 0
    call = llm.calls[0]
    assert call["model"] == "anthropic/claude-haiku-5.5"
    assert call.get("temperature") is None
    assert call["max_tokens"] == 2048
    assert call["operation"] == "verify"
    assert call["reasoning_effort"] == "low"
    assert call["response_format"] == judge.JUDGE_JSON_SCHEMA


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


@pytest.mark.relevance_real
def test_judge_populates_metadata_and_stamps_editorial_set(judge_on):
    llm = _LLM(_reply([(3, True), (2, False), (0, False)]))
    meta: dict = {}
    scores: list[int] = []
    pick = fpp._relevance_select("q", CLIPS, llm, scores_out=scores, judge_meta_out=meta)
    assert pick == 0
    assert meta["selected"] == 0
    assert meta["question_answerable"] is True
    assert len(meta["scores"]) == 3
    assert meta["scores"][0]["answers"] is True
    assert scores == [3, 2, 0]


def test_judge_editorial_set_authoritative_in_bridge():
    """Verify that an editorial set stamped from judge verdict prevents heuristic abstention."""
    from domain.first_person_decision import resolve_serve_posture
    from services.first_person_coverage import coverage_for_served_text

    editorial_set = {
        "status": "supported",
        "primary_intent": "general",
        "candidate_facets": ["general"],
        "facet_coverage": {"general": "direct"},
        "reasons": ["judge_verified_direct"],
    }
    cov = coverage_for_served_text(
        "Why did you build Ekam?",
        "Ekam is a space for transformation.",
        is_direct=True,
        editorial_set=editorial_set,
    )
    assert cov.authoritative is True
    assert cov.allow_direct is True
    assert cov.allow_related is True

    decision = resolve_serve_posture(
        pipeline_status="success",
        is_direct_answer=True,
        coverage=cov,
        assessment=None,
        primary_mode=True,
        serve_weak_match=True,
    )
    assert decision.is_direct is True
    assert decision.serves is True
    assert decision.reason == "direct"


def test_multi_dimensional_judge_reply_parsing():
    raw_payload = json.dumps(
        {
            "scores": [
                {
                    "i": 0,
                    "relevance": 3,
                    "answers": True,
                    "is_complete_thought": True,
                    "is_standalone": True,
                    "covered_facets": ["definition", "practice"],
                    "content_safety": "clean",
                },
                {
                    "i": 1,
                    "relevance": 2,
                    "answers": False,
                    "is_complete_thought": False,
                    "is_standalone": True,
                    "covered_facets": ["experience"],
                    "content_safety": "clean",
                },
            ],
            "question_answerable": True,
        }
    )
    parsed = judge.parse_judge_reply(raw_payload, 2)
    assert parsed is not None
    scores, answerable = parsed
    assert answerable is True
    assert len(scores) == 2
    assert scores[0]["is_complete_thought"] is True
    assert scores[0]["is_standalone"] is True
    assert scores[0]["covered_facets"] == ["definition", "practice"]
    assert scores[0]["content_safety"] == "clean"
    assert scores[1]["is_complete_thought"] is False


def test_select_index_filters_incomplete_and_unsafe_clips():
    scores = [
        {
            "i": 0,
            "relevance": 3,
            "answers": True,
            "is_complete_thought": False,
            "is_standalone": True,
            "content_safety": "clean",
        },
        {
            "i": 1,
            "relevance": 3,
            "answers": True,
            "is_complete_thought": True,
            "is_standalone": False,
            "content_safety": "clean",
        },
        {
            "i": 2,
            "relevance": 3,
            "answers": True,
            "is_complete_thought": True,
            "is_standalone": True,
            "content_safety": "clinical_promise",
        },
        {
            "i": 3,
            "relevance": 3,
            "answers": True,
            "is_complete_thought": True,
            "is_standalone": True,
            "content_safety": "clean",
        },
    ]
    # Clips 0 (incomplete), 1 (not standalone), and 2 (clinical promise) must be filtered out
    chosen = judge.select_index(scores, answerable=True, minimum=3)
    assert chosen == 3


def test_build_editorial_set_from_judge():
    judge_meta = {
        "scores": [
            {
                "i": 0,
                "relevance": 3,
                "answers": True,
                "is_complete_thought": True,
                "is_standalone": True,
                "covered_facets": ["practice", "cause"],
                "content_safety": "clean",
            }
        ],
        "question_answerable": True,
        "selected": 0,
    }
    ed_set = judge.build_editorial_set_from_judge(judge_meta, query="How do I practice?")
    assert ed_set is not None
    assert ed_set["status"] == "supported"
    assert "practice" in ed_set["candidate_facets"]
    assert ed_set["facet_coverage"]["practice"] == "direct"
    assert ed_set["is_complete_thought"] is True
    assert ed_set["content_safety"] == "clean"


