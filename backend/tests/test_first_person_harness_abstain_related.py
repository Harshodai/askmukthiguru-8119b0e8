"""Related clips on the context-harness terminal abstain (v10-only serving).

Contexts that passed every serve-time gate but scored below the relevance minimum
are offered as related, never answers, only when the flag is on and a score is >= 2.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.config import settings
from app.orchestrator import _stream_done_metadata
from app.pipeline.result import PipelineResult
from app.schemas import ChatResponse
from services.first_person_pipeline import FirstPersonPipeline
from services.serene_mind_engine import DistressLevel
from tests.test_first_person_context_serving import (  # noqa: F401  (autouse fixtures)
    TEXT_ONE,
    TEXT_TWO,
    _reset_env,
    _synthetic_rights_register,
    make_test_context,
    make_test_span,
)


def _run(monkeypatch, contexts, scores, *, flag=True):
    monkeypatch.setattr(settings, "first_person_abstain_related_clips_enabled", flag)
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", True)
    monkeypatch.setattr(settings, "first_person_harness_parallel_enabled", False)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    it = iter(scores)

    def scorer(q, cands, llm, loop, token_sink=None, scores_out=None, **kwargs):
        scores_out.append(next(it))
        return None  # below minimum

    monkeypatch.setattr("services.first_person_pipeline._relevance_select", scorer)
    store = Mock()
    store.retrieve.return_value = contexts
    legacy = Mock()
    legacy.search_hybrid.return_value = []
    legacy.collection = "first_person_v9"
    pipe = FirstPersonPipeline(store=legacy, serene_mind_engine=Mock(), context_store=store)
    pipe._serene_mind.assess_distress.return_value = None
    return pipe.execute(
        query="What is suffering?", query_dense_vector=[0.1] * 1024, cache_bypass=True
    )


def _ctx(n, text):
    return make_test_context(
        [make_test_span(n=n, text=text, start_ms=n * 20000, end_ms=n * 20000 + 9000)]
    )


def test_flag_on_offers_score_two_gated_contexts_only(monkeypatch):
    res = _run(monkeypatch, [_ctx(0, TEXT_ONE), _ctx(1, TEXT_TWO)], [2, 1])
    assert res.status == "abstained" and res.citations == []
    assert res.abstain_reason == "no_verified_clips"
    assert [c["text_snippet"] for c in res.related_clips] == [TEXT_ONE]
    assert res.related_clips[0]["is_answer"] is False


def test_flag_off_attaches_nothing(monkeypatch):
    res = _run(monkeypatch, [_ctx(0, TEXT_ONE)], [2], flag=False)
    assert res.related_clips == [] and "related_clips" not in res.to_dict()


def test_gate_failed_context_is_never_offered(monkeypatch):
    bad = make_test_context([make_test_span(n=0, text=TEXT_ONE, rights_cleared=False)])
    res = _run(monkeypatch, [bad], [3])
    assert res.related_clips == []


def test_scores_below_two_offer_nothing(monkeypatch):
    assert _run(monkeypatch, [_ctx(0, TEXT_ONE)], [1]).related_clips == []


def test_best_first_and_capped_at_three(monkeypatch):
    ctxs = [_ctx(i, TEXT_ONE if i % 2 else TEXT_TWO) for i in range(5)]
    res = _run(monkeypatch, ctxs, [2, 2, 2, 2, 2])
    assert len(res.related_clips) == 3


def test_crisis_never_offers_related(monkeypatch):
    monkeypatch.setattr(settings, "first_person_abstain_related_clips_enabled", True)
    store = Mock()
    pipe = FirstPersonPipeline(store=Mock(), serene_mind_engine=Mock(), context_store=store)
    pipe._serene_mind.assess_distress.return_value = Mock(level=DistressLevel.CRISIS)
    res = pipe.execute(
        query="I want to end my life", query_dense_vector=[0.1] * 1024, cache_bypass=True
    )
    assert res.related_clips == []


def _abstain_result():
    return PipelineResult(
        final_answer="x",
        intent="QUERY",
        trace_id="t",
        latency_ms=1,
        route_decision="first_person_abstain",
        route_metadata={"related_clips": [{"text_snippet": TEXT_ONE, "is_answer": False}]},
    )


def test_serializers_carry_related_clips():
    res = _abstain_result()
    assert res.to_chat_response()["related_clips"][0]["text_snippet"] == TEXT_ONE
    assert _stream_done_metadata(res)["related_clips"][0]["text_snippet"] == TEXT_ONE
    assert (
        ChatResponse(**{**res.to_chat_response(), "response": "x"}).related_clips[0]["is_answer"]
        is False
    )
    assert res.citations == []


@pytest.mark.parametrize("relpath", ["orchestrator.py", "api/chat.py"])
def test_chat_response_builders_set_related_clips(relpath):
    import ast
    from pathlib import Path

    tree = ast.parse((Path(__file__).resolve().parents[1] / "app" / relpath).read_text())
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", getattr(n.func, "attr", "")) == "ChatResponse"
        and any(k.arg for k in n.keywords)
    ]
    assert calls and all("related_clips" in {k.arg for k in c.keywords} for c in calls)
