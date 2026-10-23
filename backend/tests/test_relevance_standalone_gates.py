"""Quality gates added 2026-10-11 after an independent judge rejected 10/24 live-served clips.

* Standalone backstop (deterministic): clips cut mid-thought or tied to a one-off event.
* Relevance gate (LLM scores only): serve the best of the top candidates scoring >= min, else abstain.
Fixture: tests/fixtures/served_clips_v8_judged.json (real served clips; the labels below are the
judge's verdicts, SHOW = 1,10,12,13; clear DON'T = 4,5,7,11,14,15,16,19,22,23).
"""

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.config import settings
from services.first_person_pipeline import (
    FirstPersonPipeline,
    _relevance_select,
    _standalone_problem,
)

_CLIPS = json.loads(
    (Path(__file__).parent / "fixtures" / "served_clips_v8_judged.json").read_text(encoding="utf-8")
)


def _text(n: int) -> str:
    return _CLIPS[n - 1]["verbatim_text"]


@pytest.fixture(autouse=True)
def _default_relevance_model(monkeypatch):
    """Keep relevance model default empty for comma-separated parsing tests."""
    monkeypatch.setattr(settings, "first_person_relevance_model", "")
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", False)


# ---- deterministic standalone backstop -------------------------------------------------


@pytest.mark.parametrize("n", [1, 10, 12, 13])
def test_judge_approved_clips_pass_the_standalone_backstop(n):
    assert _standalone_problem(_text(n)) is None


@pytest.mark.parametrize("n", [4, 5, 14, 15, 16, 19, 23])
def test_judge_rejected_clips_are_caught_by_the_standalone_backstop(n):
    assert _standalone_problem(_text(n)) is not None


def test_lowercase_start_and_missing_full_stop_are_not_penalised():
    # Whisper casing/punctuation is unreliable: a good guided-practice clip ends with no full stop.
    assert (
        _standalone_problem("place your palms on your thighs and slowly move into a state of calm")
        is None
    )


def test_so_opener_is_a_fine_opener():
    assert (
        _standalone_problem("So both Preethaji and I travel across the world and meet people.")
        is None
    )


# ---- relevance selection (LLM scores only) ---------------------------------------------


class _SyncLLM:
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc, self.calls = reply, exc, []

    def generate(self, system_prompt="", user_prompt="", **kw):
        self.calls.append((system_prompt, user_prompt))
        if self.exc:
            raise self.exc
        return self.reply


pytestmark_rel = pytest.mark.relevance_real


@pytest.mark.relevance_real
@pytest.mark.parametrize(
    "reply,expected",
    [
        ("3,1,0", 0),
        ("1,3,2", 1),  # best score wins
        ("0,2,2", 1),  # tie -> earliest
        ("1,1,0", None),  # nothing reaches min score 2
        ("2,3", -1),  # wrong count -> indeterminate
        ("3,1,9", -1),  # out-of-range
        ("three,1,0", -1),  # not integers
        ("I think clip 1", -1),
        ("", -1),
    ],
)
def test_relevance_select_strict_parse(reply, expected, monkeypatch):
    # Parsing subject only: pin the threshold so a default change cannot move it.
    monkeypatch.setattr(settings, "first_person_relevance_min_score", 2)
    clips = [{"verbatim_text": f"clip {i}"} for i in range(3)]
    assert _relevance_select("q?", clips, _SyncLLM(reply)) == expected


@pytest.mark.relevance_real
def test_relevance_select_fails_closed_without_llm_or_on_error():
    clips = [{"verbatim_text": "a"}, {"verbatim_text": "b"}]
    assert _relevance_select("q?", clips, None) == -1
    assert _relevance_select("q?", clips, _SyncLLM(exc=RuntimeError("provider down"))) == -1
    assert _relevance_select("q?", [], _SyncLLM("3")) == -1


@pytest.mark.relevance_real
def test_relevance_prompt_asks_for_scores_only_and_carries_question_and_clips():
    llm = _SyncLLM("3,0")
    _relevance_select(
        "Is it okay to cry?", [{"verbatim_text": "alpha"}, {"verbatim_text": "beta"}], llm
    )
    system, user = llm.calls[0]
    assert "ONLY with comma-separated integers" in system
    assert "Is it okay to cry?" in user and "[1] alpha" in user and "[2] beta" in user


# ---- pipeline wiring ----------------------------------------------------------------------

_GOOD_A = (
    "Suffering arises from resistance to what is. The moment you stop resisting, something "
    "shifts within you and you recognise the truth of this very moment of your life."
)
_GOOD_B = (
    "Stillness is not the absence of thought, it is the awareness in which thoughts arise and "
    "dissolve, and when you rest there, peace is already here."
)


def _clip(text, vid, dense):
    return {
        "point_id": vid,
        "video_id": vid,
        "start_ms": 65000,
        "end_ms": 85000,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "transcript_hash": hashlib.sha256(text.encode()).hexdigest(),
        "verbatim_text": text,
        "passage_dense": dense,
        "source_url": f"https://youtube.com/watch?v={vid}",
        "caption_status": "auto_transcript",
    }


class _RoutingLLM:
    """YES for the answerability gate; the configured scores for the relevance gate."""

    def __init__(self, scores):
        self.scores, self.relevance_calls = scores, 0

    async def generate(self, system_prompt="", user_prompt="", **kw):
        if "ANSWER a seeker's question" in system_prompt:
            self.relevance_calls += 1
            return self.scores
        return "YES"


def _run(scores):
    store = MagicMock()
    store.collection = "first_person_v1"
    store.search_hybrid.return_value = [
        _clip(_GOOD_A, "vidA", [1.0, 0.0]),
        _clip(_GOOD_B, "vidB", [0.9, 0.1]),
    ]
    redis = MagicMock()
    redis.get.return_value = None
    llm = _RoutingLLM(scores)
    pipeline = FirstPersonPipeline(
        store=store, redis_client=redis, calibration_profile=None, llm_service=llm
    )
    res = pipeline.execute(query="What is stillness?", query_dense_vector=[1.0, 0.0])
    return res, llm


@pytest.mark.relevance_real
def test_pipeline_serves_the_clip_the_relevance_gate_picks_even_if_not_top_ranked():
    res, llm = _run("1,3")
    assert llm.relevance_calls == 1
    assert res.status == "weak_match"
    assert res.citations[0]["video_id"] == "vidB"


@pytest.mark.relevance_real
def test_pipeline_abstains_when_no_candidate_reaches_the_minimum():
    res, _ = _run("1,0")
    assert res.status == "abstained"
    assert res.citations == []
    assert res.answerability == "relevance_below_min"


@pytest.mark.relevance_real
def test_pipeline_abstains_on_unparseable_relevance_output():
    res, _ = _run("looks fine")
    assert res.status == "abstained"
    assert res.citations == []


@pytest.mark.relevance_real
def test_relevance_gate_flag_off_restores_top_clip_without_an_llm_call(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", False)
    res, llm = _run("0,0")
    assert llm.relevance_calls == 0
    assert res.status == "weak_match"
    assert res.citations[0]["video_id"] == "vidA"


@pytest.mark.parametrize(
    "text",
    [
        "If the parents are conflicted the infant suffers a colicky stomach and cries incessantly.",
        "People bedridden with sickness and depression for years come alive with vigor.",
        "Your body got flooded by huge loads of sugar and you had to run and escape.",
        "It is scientifically proven today beyond doubt that a twenty second hug releases oxytocin.",
        "These small practices help to prevent depression in the whole family.",
        "You are sending a very wrong signal to the universe and there will come a time you will have a fall.",
    ],
)
def test_health_causal_claims_are_not_served_out_of_context(text):
    assert _standalone_problem(text) == "health_claim"


def test_depression_as_a_theme_is_not_blocked():
    # 'core of depression is a battle with oneself' (judge: SHOW) must stay servable.
    assert (
        _standalone_problem(
            "At the core of depression is a battle with oneself, an inner war that never ends."
        )
        is None
    )


@pytest.mark.relevance_real
def test_relevance_scorer_model_override_is_passed_only_when_configured(monkeypatch):
    seen = {}

    class _Llm:
        def generate(self, system_prompt="", user_prompt="", **kw):
            seen.update(kw)
            return "3"

    clips = [{"verbatim_text": "x"}]
    monkeypatch.setattr(settings, "first_person_relevance_model", "")
    _relevance_select("q?", clips, _Llm())
    assert "model" not in seen

    monkeypatch.setattr(settings, "first_person_relevance_model", "anthropic/claude-haiku-5.5")
    _relevance_select("q?", clips, _Llm())
    assert seen["model"] == "anthropic/claude-haiku-5.5" and seen["max_tokens"] == 1024
    # CA-1: Haiku 5.5 rejects non-default sampling values — temperature is
    # passed as None so the service layer omits the key.
    assert seen.get("temperature") is None


@pytest.mark.relevance_real
def test_relevance_scorer_keeps_explicit_temperature_for_other_models(monkeypatch):
    seen = {}

    class _Llm:
        def generate(self, system_prompt="", user_prompt="", **kw):
            seen.update(kw)
            return "3"

    clips = [{"verbatim_text": "x"}]
    monkeypatch.setattr(settings, "first_person_relevance_model", "deepseek/deepseek-chat")
    _relevance_select("q?", clips, _Llm())
    assert seen["model"] == "deepseek/deepseek-chat"
    assert seen.get("temperature") == 0.0


@pytest.mark.relevance_real
def test_anthropic_scorer_models_stay_in_no_temperature_set():
    """Review P3-6: swapping first_person_relevance_model to another Anthropic
    model must consciously update _SCORER_NO_TEMPERATURE_MODELS — otherwise
    CA-1 silently returns as a rejection-turned-abstain."""
    from services.first_person_pipeline import _SCORER_NO_TEMPERATURE_MODELS

    assert "anthropic/claude-haiku-5.5" in _SCORER_NO_TEMPERATURE_MODELS


@pytest.mark.relevance_real
def test_pipeline_labels_a_broken_scorer_as_indeterminate_not_below_min():
    res, _ = _run("looks fine")
    assert res.status == "abstained"
    assert res.answerability == "relevance_indeterminate"


def test_model_policy_extra_allowed_models_extends_the_enforced_allowlist_only_by_name():
    from types import SimpleNamespace

    from app.model_policy import ModelPolicyError, OpenRouterModelPolicy

    base = dict(
        openrouter_policy_id="p",
        openrouter_generation_model="deepseek/deepseek-chat-v3",
        openrouter_generation_model_fallback="meta-llama/llama-3.3-70b-instruct",
        openrouter_fast_model="meta-llama/llama-3.1-8b-instruct",
        openrouter_classify_model="meta-llama/llama-3.1-8b-instruct",
        llm_max_tokens_fast=512,
        llm_max_tokens_deep=2048,
    )
    plain = OpenRouterModelPolicy.from_settings(SimpleNamespace(**base))
    with pytest.raises(ModelPolicyError):
        plain.assert_model_allowed("anthropic/claude-sonnet-5.5")

    extended = OpenRouterModelPolicy.from_settings(
        SimpleNamespace(**base, openrouter_extra_allowed_models="anthropic/claude-sonnet-5.5")
    )
    extended.assert_model_allowed("anthropic/claude-sonnet-5.5")
    with pytest.raises(ModelPolicyError):  # everything else is still refused
        extended.assert_model_allowed("anthropic/claude-opus-5.5")


def test_transient_retrieval_disconnect_is_retried_once_not_surfaced_as_an_error():
    """Live 2026-10-11: one dropped Qdrant keep-alive connection became a 503 for a seeker."""
    store = MagicMock()
    store.collection = "first_person_v1"
    store.search_hybrid.side_effect = [
        RuntimeError("Server disconnected without sending a response."),
        [_clip(_GOOD_A, "vidA", [1.0, 0.0])],
    ]
    redis = MagicMock()
    redis.get.return_value = None
    pipeline = FirstPersonPipeline(
        store=store, redis_client=redis, calibration_profile=None, llm_service=_RoutingLLM("3")
    )
    res = pipeline.execute(query="What is stillness?", query_dense_vector=[1.0, 0.0])

    assert store.search_hybrid.call_count == 2
    assert res.status != "error"


def test_non_transient_retrieval_error_is_not_retried():
    store = MagicMock()
    store.collection = "first_person_v1"
    store.search_hybrid.side_effect = ValueError("bad filter")
    redis = MagicMock()
    redis.get.return_value = None
    pipeline = FirstPersonPipeline(
        store=store, redis_client=redis, calibration_profile=None, llm_service=_RoutingLLM("3")
    )
    res = pipeline.execute(query="What is stillness?", query_dense_vector=[1.0, 0.0])

    assert store.search_hybrid.call_count == 1
    assert res.status == "error"


# ---- quality allowlist (opt-in, fail closed) -------------------------------------------------


def _with_allowlist(monkeypatch, tmp_path, ids):
    f = tmp_path / "allow.json"
    if ids is not None:
        f.write_text(json.dumps({"approved": ids}), encoding="utf-8")
    monkeypatch.setattr(settings, "first_person_quality_allowlist_path", str(f))
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", False)


def test_allowlist_is_off_by_default():
    from services.first_person_pipeline import _quality_allowlist

    assert _quality_allowlist() is None


@pytest.mark.relevance_real
def test_allowlist_restricts_serving_to_approved_clips(monkeypatch, tmp_path):
    _with_allowlist(monkeypatch, tmp_path, ["vidB"])
    res, _ = _run("3,3")
    assert res.status == "weak_match"
    assert res.citations[0]["video_id"] == "vidB"  # vidA ranks first but is not approved


@pytest.mark.relevance_real
def test_empty_allowlist_serves_nothing(monkeypatch, tmp_path):
    _with_allowlist(monkeypatch, tmp_path, [])
    res, _ = _run("3,3")
    assert res.status == "abstained" and res.citations == []


@pytest.mark.relevance_real
def test_missing_allowlist_file_fails_closed(monkeypatch, tmp_path):
    _with_allowlist(monkeypatch, tmp_path, None)  # path configured, file never written
    res, _ = _run("3,3")
    assert res.status == "abstained" and res.citations == []


def test_allowlist_reloads_when_the_file_changes(monkeypatch, tmp_path):
    import os

    from services.first_person_pipeline import _quality_allowlist

    _with_allowlist(monkeypatch, tmp_path, ["a"])
    assert _quality_allowlist() == frozenset({"a"})
    f = tmp_path / "allow.json"
    f.write_text(json.dumps(["a", "b"]), encoding="utf-8")
    os.utime(f, (os.path.getmtime(f) + 5, os.path.getmtime(f) + 5))
    assert _quality_allowlist() == frozenset({"a", "b"})


def test_relevance_select_scores_full_clip_text_not_truncated(monkeypatch):
    """QBUG-7: the scorer sees the whole clip — an answer past char 450 must
    reach the model, not be cut mid-clip. Unmarked (no real LLM): stub only."""
    monkeypatch.setattr(settings, "first_person_relevance_min_score", 2)
    head = "Opening theme words. " * 30  # >450 chars of theme, no answer
    tail = "The direct answer: practice stillness every morning."
    clips = [{"verbatim_text": head + tail}]
    llm = _SyncLLM("3")
    assert _relevance_select("What should I practice?", clips, llm) == 0
    sent_prompt = llm.calls[0][1]
    assert tail in sent_prompt


@pytest.mark.relevance_real
def test_second_quote_is_off_by_default_and_serves_one_citation():
    res, _ = _run("3,3")
    assert len(res.citations) == 1


@pytest.mark.relevance_real
def test_second_quote_serves_two_labelled_separate_recordings(monkeypatch):
    monkeypatch.setattr(settings, "first_person_second_quote_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_min_score", 3)
    monkeypatch.setattr(
        "services.first_person_pipeline.is_youtube_video_available", lambda _v: True
    )
    res, _ = _run("3,3")
    assert res.status == "weak_match"
    assert [c["video_id"] for c in res.citations] == ["vidA", "vidB"]
    assert "Recording 1 of 2" in res.answer_text and "Recording 2 of 2" in res.answer_text
    assert "does not continue the first" in res.answer_text
    # both quotes are the stored text, byte for byte
    assert _GOOD_A in res.answer_text and _GOOD_B in res.answer_text


@pytest.mark.relevance_real
def test_second_quote_needs_the_second_clip_to_reach_the_minimum(monkeypatch):
    monkeypatch.setattr(settings, "first_person_second_quote_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_min_score", 3)
    monkeypatch.setattr(
        "services.first_person_pipeline.is_youtube_video_available", lambda _v: True
    )
    res, _ = _run("3,2")
    assert len(res.citations) == 1 and "Recording 2" not in res.answer_text


def test_anger_at_spouse_triggers_relationship_boundary() -> None:
    from guardrails.lightweight_handler import needs_relationship_safety_boundary as n

    assert n("How do I deal with anger at my husband?")
    assert n("My wife and I fight every day, what do I do?")
    assert not n("What is the Beautiful State?")
    assert not n("Why am I so angry at work?")


def test_violence_wording_excluded_only_for_relationship_questions() -> None:
    from services.first_person_pipeline import _violent_for_context as v

    clip = "As a husband, he doesn't mind being stabbed by his angry wife to calm her down."
    assert v("How do I deal with anger at my husband?", clip)
    assert not v("What is the Beautiful State?", clip)
    assert not v("How do I deal with anger at my husband?", "Breathe and feel your body.")
    assert v("How do I deal with anger at my husband?", "he even tried to choke him to death.")
    # Possessive object matches for hit
    assert v(
        "How do I deal with anger at my husband?", "In anger a person may hit his wife or husband."
    )
    assert v(
        "My wife and I fight every day, what do I do?",
        "He was hitting my husband during the dispute.",
    )
    assert v("How do I deal with anger at my husband?", "A man must never hit a woman.")
    assert v("How do I deal with anger at my husband?", "He admitted to hitting his pregnant wife.")
    assert v("How do I deal with anger at my husband?", "He wanted to hit someone in anger.")
    # Passive assault wording
    assert v(
        "How do I deal with anger at my husband?",
        "She said she was hit by her husband in the argument.",
    )
    assert v(
        "How do I deal with anger at my husband?",
        "A person who was hit by his wife feels humiliated.",
    )
    assert v(
        "My partner's fury is hurting our family", "She got hit by her partner during a fight."
    )
    # Kicking forms
    assert v("How do I deal with anger at my husband?", "He kicked the person in frustration.")
    assert v("My wife and I fight every day, what do I do?", "He started kicking the door and her.")
    assert v(
        "How do I deal with anger at my husband?", "In anger one kicks out at those they love."
    )
    assert not v("How do I deal with anger at my husband?", "We hit a wall in our discussions.")
    assert not v(
        "How do I deal with anger at my husband?", "They hit the road early in the morning."
    )
    # Retrieval query triggers boundary even if original query was translated
    assert v("Hindi question", clip, retrieval_query="How do I deal with anger at my husband?")
    assert not v("Hindi question", clip, retrieval_query="What is the Beautiful State?")
    # Stable / stability do not trigger violence filter
    assert not v(
        "How do I deal with anger at my husband?", "Cultivate emotional stability and peace."
    )
    assert not v(
        "How do I deal with anger at my husband?", "A stable mind is free from turbulence."
    )
    # Fury triggers relationship repair boundary
    assert v("My partner's fury is hurting our family", "He tried to choke her.")
