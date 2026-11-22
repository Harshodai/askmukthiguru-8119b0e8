"""Serve-rate flags of 2026-11-19 (battery: conversation turns 9/32, complex 7/15).

Every flag is default off; each test pins both states. Invariants pinned here: the
evidence body stays verbatim (notes ride in safety_notices), the scorer's strict
count check is unchanged, and reordering never drops a candidate.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import services.first_person_pipeline as fpp
from app.config import settings
from app.pipeline.stages import first_person_bridge as bridge
from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
from rag.resolve_followup import meta_followup_kind, strip_topic_shift
from tests.test_first_person_bridge import (  # noqa: F401 - fixtures
    _bridge_gates,
    _container,
    _ctx,
    _fp_result,
    fp_pipeline,
)

_FLAGS = (
    "first_person_meta_followup_enabled",
    "first_person_topic_shift_enabled",
    "first_person_relevance_exact_n_enabled",
    "first_person_context_seen_rerank_enabled",
    "first_person_answerability_prefetch_enabled",
    "first_person_multipart_enabled",
)


def test_every_new_flag_defaults_off():
    from app.config import Settings

    for name in _FLAGS:
        assert Settings.model_fields[name].default is False, name


# --- (a) meta follow-ups and topic shifts -------------------------------------------


@pytest.mark.parametrize(
    "turn,kind",
    [
        ("That is too long, can you say it shorter?", "shorter"),
        ("Can you give me an example of what to do in the moment?", "example"),
        ("Can you explain the second one?", "ordinal"),
        ("What did you mean by that?", "elaborate"),
        ("Can you explain that more simply?", "elaborate"),
        ("How do I practise it?", "elaborate"),
        ("How do I calm an anxious mind?", None),
        ("What is the purpose of meditation?", None),
        ("Unrelated, can you say it shorter?", None),  # an explicit shift is never meta
        (
            "I keep giving my son examples of good behaviour but he never listens to me at all",
            None,
        ),
    ],
)
def test_meta_followup_kind(turn, kind):
    assert meta_followup_kind(turn) == kind


@pytest.mark.parametrize(
    "turn,rest",
    [
        ("Unrelated, what is the purpose of meditation?", "what is the purpose of meditation?"),
        ("New question: what is karma?", "what is karma?"),
        ("Okay, changing the topic - what is ego?", "what is ego?"),
        ("I feel different today", None),
        ("Okay, back to my father: what if he never apologises?", None),
        ("Unrelated, ok", None),  # nothing left to ask
    ],
)
def test_strip_topic_shift(turn, rest):
    assert strip_topic_shift(turn) == rest


_HIST = [
    {"role": "user", "content": "I am anxious all the time about the future."},
    {"role": "assistant", "content": "(clip)"},
]


def test_resolve_meta_followup_is_inert_with_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "first_person_meta_followup_enabled", False)
    assert bridge._resolve_meta_followup("can you say it shorter?", _HIST) is None


def test_topic_shift_is_independent_of_the_meta_flag(monkeypatch):
    """Split 2026-11-22: a mis-serve protection must not ride on the meta lane's flag."""
    monkeypatch.setattr(settings, "first_person_meta_followup_enabled", False)
    monkeypatch.setattr(settings, "first_person_topic_shift_enabled", True)
    shifted = bridge._resolve_topic_shift("Unrelated, what is karma?")
    assert shifted is not None and shifted.retrieval_query == "what is karma?"
    # ...and the meta lane stays inert on the same turn.
    assert bridge._resolve_meta_followup("Unrelated, what is karma?", _HIST) is None
    # With the topic-shift flag off, nothing is stripped (pre-split behaviour).
    monkeypatch.setattr(settings, "first_person_topic_shift_enabled", False)
    assert bridge._resolve_topic_shift("Unrelated, what is karma?") is None


def test_resolve_meta_followup_targets_the_prior_turn(monkeypatch):
    monkeypatch.setattr(settings, "first_person_meta_followup_enabled", True)
    prior = _HIST[0]["content"]
    res = bridge._resolve_meta_followup("That is too long, can you say it shorter?", _HIST)
    assert (res.retrieval_query, res.max_context_spans) == (prior, 1)
    assert "shorter" in res.note and res.kind == "shorter"
    res = bridge._resolve_meta_followup("Give me an example?", _HIST)
    assert res.retrieval_query.startswith(prior) and res.max_context_spans is None
    assert "example" in res.note and res.kind == "example"
    # A topic shift is no longer this function's job (see _resolve_topic_shift).
    assert bridge._resolve_meta_followup("Unrelated, what is karma?", _HIST) is None
    # No prior user turn (or only the current one): nothing to resolve against.
    assert bridge._resolve_meta_followup("say it shorter", []) is None
    assert (
        bridge._resolve_meta_followup("say it shorter", [{"role": "user", "content": "say it shorter"}])
        is None
    )


@pytest.mark.parametrize("flag", [False, True])
@pytest.mark.asyncio
async def test_bridge_meta_followup_query_note_and_span_cap(monkeypatch, fp_pipeline, flag):  # noqa: F811
    monkeypatch.setattr(settings, "first_person_meta_followup_enabled", flag)
    monkeypatch.setattr(settings, "first_person_topic_shift_enabled", False)
    ctx = _ctx(_container(), msg="That is too long, can you say it shorter?")
    ctx.chat_body_messages = list(_HIST)
    result = await FirstPersonBridgeStage().run(ctx)
    kw = fp_pipeline.execute.call_args.kwargs
    if not flag:
        # Old resolver: the meta request itself is glued on and scored (the live bug).
        assert kw["retrieval_query"] == f"{_HIST[0]['content']} — That is too long, can you say it shorter?"
        assert "max_context_spans" not in kw
        return
    assert kw["retrieval_query"] == _HIST[0]["content"]
    assert kw["max_context_spans"] == 1 and kw["cache_bypass"] is True
    # The note is platform copy; the evidence body is the verbatim quote only.
    notices = result.route_metadata["safety_notices"]
    assert bridge._META_FOLLOWUP_NOTES["shorter"] in notices
    assert bridge._META_FOLLOWUP_NOTES["shorter"] not in result.final_answer


@pytest.mark.asyncio
async def test_bridge_topic_shift_strips_marker_and_ignores_history(monkeypatch, fp_pipeline):  # noqa: F811
    # The topic-shift flag alone: the meta lane stays off (2026-11-22 split).
    monkeypatch.setattr(settings, "first_person_meta_followup_enabled", False)
    monkeypatch.setattr(settings, "first_person_topic_shift_enabled", True)
    ctx = _ctx(_container(), msg="Unrelated, what is the purpose of meditation?")
    ctx.chat_body_messages = [{"role": "user", "content": "How do I forgive my father?"}]
    await FirstPersonBridgeStage().run(ctx)
    kw = fp_pipeline.execute.call_args.kwargs
    assert kw["retrieval_query"] == "what is the purpose of meditation?"
    assert kw["query"] == "Unrelated, what is the purpose of meditation?"  # safety sees it raw


@pytest.mark.asyncio
async def test_both_followup_flags_off_keep_the_pre_split_behaviour(monkeypatch, fp_pipeline):  # noqa: F811
    """Behaviour-neutral split: with both flags off nothing is rewritten and no cache is bypassed."""
    monkeypatch.setattr(settings, "first_person_meta_followup_enabled", False)
    monkeypatch.setattr(settings, "first_person_topic_shift_enabled", False)
    ctx = _ctx(_container(), msg="Unrelated, what is the purpose of meditation?")
    ctx.chat_body_messages = [{"role": "user", "content": "How do I forgive my father?"}]
    await FirstPersonBridgeStage().run(ctx)
    kw = fp_pipeline.execute.call_args.kwargs
    assert kw["retrieval_query"] == "Unrelated, what is the purpose of meditation?"
    assert kw["cache_bypass"] is False


# --- (b) multi-part questions --------------------------------------------------------


@pytest.mark.parametrize(
    "q,parts",
    [
        (
            "What is the difference between Serene Mind and Soul Sync, and which should I do first?",
            ["What is Serene Mind?", "What is Soul Sync?"],
        ),
        ("What is the ego, and is it bad?", ["What is the ego", "What is the ego — is it bad?"]),
        ("How do I calm an anxious mind?", []),
        ("Is karma real, or is it just a story we tell ourselves?", []),
    ],
)
def test_question_parts(q, parts):
    assert bridge._question_parts(q) == parts


@pytest.mark.parametrize("flag", [False, True])
@pytest.mark.asyncio
async def test_bridge_multipart_serves_each_part(monkeypatch, fp_pipeline, flag):  # noqa: F811
    monkeypatch.setattr(settings, "first_person_multipart_enabled", flag)
    from tests.test_first_person_bridge import _clip_citation

    other_text = "Soul Sync is a practice of breath and stillness that brings you home to yourself."
    other = _fp_result(answer=other_text, citations=[_clip_citation(verbatim_text=other_text)])
    if flag:
        fp_pipeline.execute.side_effect = [_fp_result(), other]
    q = "What is the difference between Serene Mind and Soul Sync?"
    result = await FirstPersonBridgeStage().run(_ctx(_container(), msg=q))
    asked = [c.kwargs["retrieval_query"] for c in fp_pipeline.execute.call_args_list]
    if not flag:
        assert asked == [q]
        return
    assert asked == ["What is Serene Mind?", "What is Soul Sync?"]
    notes = " ".join(result.route_metadata["safety_notices"])
    assert "not a combined answer" in notes


@pytest.mark.asyncio
async def test_multipart_falls_back_to_whole_question_when_no_part_serves(monkeypatch, fp_pipeline):  # noqa: F811
    monkeypatch.setattr(settings, "first_person_multipart_enabled", True)
    abstain = SimpleNamespace(**{**vars(_fp_result()), "status": "abstained", "citations": []})
    served = _fp_result()
    fp_pipeline.execute.side_effect = [abstain, abstain, served]
    q = "What is the difference between Serene Mind and Soul Sync?"
    await FirstPersonBridgeStage().run(_ctx(_container(), msg=q))
    asked = [c.kwargs["retrieval_query"] for c in fp_pipeline.execute.call_args_list]
    assert asked[-1] == q and len(asked) == 3


def test_merge_keeps_only_served_parts_and_their_order():
    a, b = _fp_result(answer="A"), _fp_result(answer="B", status="weak_match")
    merged = bridge._merge_part_results([a, None, b])
    assert merged.answer_text == "A\n\nB" and merged.status == "weak_match"
    assert merged.is_direct_answer is True and len(merged.citations) == 2


# --- (c) exactly-N scorer ------------------------------------------------------------


class _LLM:
    def __init__(self, reply: str):
        self.reply, self.kwargs = reply, {}

    async def generate(self, system_prompt, user_prompt, **kw):
        self.kwargs = {"system_prompt": system_prompt, **kw}
        return self.reply


def _score(llm, n=1):
    clips = [{"verbatim_text": f"clip {i}"} for i in range(n)]
    return asyncio.run(fpp._relevance_select_scored_async("q?", clips, llm))


@pytest.mark.parametrize("model", ["anthropic/claude-haiku-5.5", "deepseek/deepseek-chat"])
def test_exact_n_off_keeps_the_old_contract(monkeypatch, model):
    monkeypatch.setattr(settings, "first_person_relevance_exact_n_enabled", False)
    monkeypatch.setattr(settings, "first_person_relevance_model", model)
    llm = _LLM('{"scores": [3]}' if model.startswith("anthropic") else "3")
    assert _score(llm) == 0
    assert "3,1,0" in llm.kwargs["system_prompt"] or "[3, 1, 0]" in llm.kwargs["system_prompt"]


def test_exact_n_json_path_uses_keyed_schema(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_exact_n_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_model", "anthropic/claude-haiku-5.5")
    llm = _LLM('{"clip_1": 3, "clip_2": 0}')
    assert _score(llm, n=2) == 0
    schema = llm.kwargs["response_format"]["json_schema"]["schema"]
    assert schema["required"] == ["clip_1", "clip_2"] and schema["additionalProperties"] is False
    # A wrong key set is still indeterminate: the strict check is unchanged.
    assert _score(_LLM('{"clip_1": 3}'), n=2) == fpp._RELEVANCE_INDETERMINATE
    assert _score(_LLM('{"scores": [3, 0]}'), n=2) == fpp._RELEVANCE_INDETERMINATE


def test_exact_n_comma_path_example_has_length_n(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_exact_n_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_model", "deepseek/deepseek-chat")
    llm = _LLM("3")
    assert _score(llm) == 0
    prompt = llm.kwargs["system_prompt"]
    # The rubric and its anchoring examples are untouched; only the count is appended.
    assert prompt.startswith(fpp._RELEVANCE_SYSTEM_PROMPT) and prompt.endswith(
        "exactly 1 clip(s): reply with exactly 1 integer(s)."
    )
    assert _score(_LLM("3,1,0")) == fpp._RELEVANCE_INDETERMINATE  # miscount stays indeterminate


def test_exact_n_rekeys_the_exact_cache_only_when_on(monkeypatch):
    from unittest.mock import Mock

    pipeline = fpp.FirstPersonPipeline(store=Mock(), redis_client=Mock(), serene_mind_engine=Mock())
    monkeypatch.setattr(settings, "first_person_relevance_exact_n_enabled", False)
    off = pipeline._serving_policy_components()
    monkeypatch.setattr(settings, "first_person_relevance_exact_n_enabled", True)
    on = pipeline._serving_policy_components()
    assert "relevance_exact_n" not in off and on["relevance_exact_n"] == "keyed_v2"


# --- (d) seen-clip reorder on the harness path ---------------------------------------


def _context(video: str, span: str):
    return SimpleNamespace(
        parent=SimpleNamespace(video_id=video), spans=[SimpleNamespace(source_span_id=span)]
    )


@pytest.mark.parametrize("flag", [False, True])
def test_seen_contexts_go_last_without_dropping_any(monkeypatch, flag):
    monkeypatch.setattr(settings, "first_person_context_seen_rerank_enabled", flag)
    ctxs = [_context("v1", "s1"), _context("v2", "s2"), _context("v3", "s3")]
    out = fpp.FirstPersonPipeline._seen_contexts_last(
        ctxs, {"seen_video_ids": ["v1"], "seen_clip_ids": ["s2"]}
    )
    assert sorted(map(id, out)) == sorted(map(id, ctxs))
    assert [c.parent.video_id for c in out] == (["v1", "v2", "v3"] if not flag else ["v3", "v1", "v2"])


# --- (e) answerability prefetch ------------------------------------------------------


def test_prefetch_is_none_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "first_person_answerability_prefetch_enabled", False)

    async def _run():
        return fpp.start_answerability_prefetch(object(), "q")

    assert asyncio.run(_run()) is None


def test_prefetch_for_another_question_is_cancelled_not_used():
    async def _run():
        task = asyncio.ensure_future(asyncio.sleep(10, result=True))
        assert fpp._take_answerability_prefetch(("other", task, []), "q") is None
        await asyncio.sleep(0)
        return task.cancelled()

    assert asyncio.run(_run()) is True


def test_prefetch_starts_and_its_verdict_is_reused(monkeypatch):
    monkeypatch.setattr(settings, "first_person_answerability_prefetch_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    calls: list[str] = []

    async def fake_gate(question, llm, request_loop=None, token_sink=None):
        calls.append(question)
        token_sink.append(7)
        return True

    def sync_gate(*a, **k):  # the module global the harness calls through _acall
        raise AssertionError("sync path must not run")

    sync_gate._async_core = fake_gate
    monkeypatch.setattr(fpp, "_answerability_check", sync_gate)

    async def _run():
        pipeline = fpp.FirstPersonPipeline.__new__(fpp.FirstPersonPipeline)
        pipeline._llm_service, pipeline._llm_loop = object(), asyncio.get_running_loop()
        pre = fpp.start_answerability_prefetch(pipeline, "q")
        task, tokens = fpp._take_answerability_prefetch(pre, "q")
        return await task, tokens

    assert asyncio.run(_run()) == (True, [7])
    assert calls == ["q"]


def test_keyed_scores_parser_rejects_extra_keys_and_bools():
    assert fpp._parse_keyed_scores(json.loads('{"clip_1": 2}'), 1) == [2]
    for bad in ('{"clip_1": 2, "x": 1}', '{"clip_1": true}', "[2]"):
        with pytest.raises(ValueError):
            fpp._parse_keyed_scores(json.loads(bad), 1)


# Prefetch must change timing only: every harness golden replays byte-identically.
# (2026-11-19: the first prefetch branch left `ans_str` unset; every live turn raised
# UnboundLocalError and abstained. Unit tests on the helpers alone did not catch it.)
import tests.test_first_person_pipeline_golden_llm as _t702  # noqa: E402
from tests.test_first_person_pipeline_golden import _deterministic_settings  # noqa: E402,F401
from tests.test_first_person_pipeline_golden_llm import _llm_settings  # noqa: E402,F401


@pytest.mark.answerability_real
@pytest.mark.relevance_real
@pytest.mark.parametrize("case", sorted(c for c in _t702.SCENARIOS if c.startswith("harness_")))
def test_prefetch_replays_every_harness_golden(case, monkeypatch):
    monkeypatch.setattr(settings, "first_person_answerability_prefetch_enabled", True)
    pipeline, kwargs = _t702.SCENARIOS[case](monkeypatch)

    async def _run():
        pipeline._llm_loop = asyncio.get_running_loop()
        pre = fpp.start_answerability_prefetch(pipeline, kwargs["query"])
        if settings.first_person_answerability_check_enabled:
            assert pre is not None
        return await fpp.serve_first_person(
            pipeline,
            query_dense_vector=[1.0, 0.0],
            cache_bypass=True,
            **kwargs,
            **({"answerability_prefetch": pre} if pre else {}),
        )

    result = asyncio.run(_run())
    observed = _t702._observe(pipeline, result, case)
    expected = json.loads((_t702.GOLDEN_DIR / f"{case}.json").read_text(encoding="utf-8"))
    assert observed == expected, f"{case}: prefetch changed behaviour"


@pytest.mark.answerability_real
@pytest.mark.relevance_real
@pytest.mark.parametrize("flags_on", [False, True])
def test_bridge_with_real_pipeline_serves_with_every_flag(flags_on, monkeypatch):
    """End to end through the real harness: every flag on must still serve the clip."""
    from unittest.mock import MagicMock

    from tests.test_first_person_async_lane import _loop_pipeline
    from tests.test_first_person_pipeline_golden_llm import FakeLLM

    for name in _FLAGS:
        monkeypatch.setattr(settings, name, flags_on)
    for name in ("first_person_context_harness_enabled", "first_person_answerability_check_enabled",
                 "first_person_relevance_gate_enabled", "first_person_chat_bridge_enabled",
                 "first_person_route_enabled"):
        monkeypatch.setattr(settings, name, True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    monkeypatch.setattr(settings, "first_person_relevance_model", "")
    monkeypatch.setattr(fpp, "_REQUEST_LOOP", None)

    async def _run():
        pipeline = _loop_pipeline(asyncio.get_running_loop())
        pipeline._llm_service = FakeLLM()
        pipeline.execute = MagicMock(side_effect=AssertionError("sync entry used on the loop"))
        monkeypatch.setattr(bridge, "_fp_pipeline", lambda container: pipeline)
        res = await FirstPersonBridgeStage().run(_ctx(_container(), msg="What is the nature of suffering?"))
        return pipeline, res

    pipeline, res = asyncio.run(_run())
    assert res is not None
    assert res.route_metadata["route_decision"] == "first_person_bridge"
    assert res.citations, "the clip must still be served"
    assert pipeline._llm_service.calls.count("answerability") == 1  # prefetch never doubles the gate call



@pytest.mark.asyncio
async def test_topic_shift_bypasses_the_exact_cache(monkeypatch, fp_pipeline):  # noqa: F811
    monkeypatch.setattr(settings, "first_person_meta_followup_enabled", False)
    monkeypatch.setattr(settings, "first_person_topic_shift_enabled", True)
    await FirstPersonBridgeStage().run(_ctx(_container(), msg="Unrelated, what is the purpose of meditation?"))
    assert fp_pipeline.execute.call_args.kwargs["cache_bypass"] is True


@pytest.mark.asyncio
async def test_multipart_answer_is_rechecked_against_the_whole_question(monkeypatch, fp_pipeline):  # noqa: F811
    monkeypatch.setattr(settings, "first_person_multipart_enabled", True)
    seen = []

    class _Unsafe:
        may_serve, reason_codes = False, ("external_teacher",)

    def _assess(query, text, retrieval_query=""):
        seen.append(query)
        return _Unsafe()

    monkeypatch.setattr(
        "services.first_person_evidence_policy.first_person_evidence_policy.assess_contextual_safety",
        _assess,
    )
    q = "What is the difference between Serene Mind and Soul Sync?"
    await FirstPersonBridgeStage().run(_ctx(_container(), msg=q))
    asked = [c.kwargs["retrieval_query"] for c in fp_pipeline.execute.call_args_list]
    assert q in seen  # the whole question was checked
    assert asked[-1] == q  # unsafe combination -> whole question served the normal way


@pytest.mark.asyncio
async def test_multipart_never_serves_the_same_clip_twice(monkeypatch, fp_pipeline):  # noqa: F811
    monkeypatch.setattr(settings, "first_person_multipart_enabled", True)
    fp_pipeline.execute.return_value = _fp_result()  # both parts get the identical clip
    q = "What is the difference between Serene Mind and Soul Sync?"
    result = await FirstPersonBridgeStage().run(_ctx(_container(), msg=q))
    assert len(result.citations) == 1
    assert "only one part" in " ".join(result.route_metadata["safety_notices"])


def test_meta_followup_skips_a_prior_turn_that_is_itself_meta(monkeypatch):
    """battery 2026-11-19: "What did you mean by that?" resolved to "Can you explain the
    second one?" (a meta turn) and re-served an unrelated clip."""
    monkeypatch.setattr(settings, "first_person_meta_followup_enabled", True)
    hist = [
        {"role": "user", "content": "What are the four sacred secrets?"},
        {"role": "assistant", "content": "(abstain)"},
        {"role": "user", "content": "Can you explain the second one?"},
    ]
    res = bridge._resolve_meta_followup("What did you mean by that?", hist)
    assert res.retrieval_query == "What are the four sacred secrets?"
    # Anonymous turns carry only the last prior user turn: a meta-only chain resolves to nothing.
    assert bridge._resolve_meta_followup("What did you mean by that?", hist[2:]) is None
