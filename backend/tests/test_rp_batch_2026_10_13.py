"""RP batch 2026-10-13: RP-C3, RP-C6, RP-C10, RP-A5, RP-A9.

Fail-before / pass-after tests for the prod-readiness task list items.
All tests are host-side unit tests: no containers, no network, no paid calls.
"""

import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest

from app import metrics as metrics_mod
from app.config import settings


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


_GOOD_A = (
    "Suffering arises from resistance to what is. The moment you stop resisting, something "
    "shifts within you and you recognise the truth of this very moment of your life."
)
_GOOD_B = (
    "Stillness is not the absence of thought, it is the awareness in which thoughts arise and "
    "dissolve, and when you rest there, peace is already here."
)


class _SyncLLM:
    """Single canned reply for every gate (relevance + rerank + answerability).

    Routing rules (mirrors _ThreeKindLLM from test_slice_d_second_quote):
    - Answerability gate  → always "YES" (so relevance scorer is always reached)
    - LLM reranker        → "1,2" (keeps both clips in the natural retrieval
                            order — see generate below; the relevance scorer
                            ranks them, not this reply)
    - Relevance gate (JSON schema path, Haiku 5.5) → wraps CSV scores as JSON
    - Relevance gate (CSV path) → returns reply as-is
    """

    # Substring unique to the answerability system prompt — avoids importing the constant.
    _ANSWERABILITY_MARKER = "You are a question classifier for AskMukthiGuru"
    # Unique phrase in the LLM-reranker system prompt (services/first_person_pipeline.py).
    _RERANKER_MARKER = "rank the clips from most to least relevant"

    def __init__(self, reply):
        self.reply = reply

    def generate(self, system_prompt="", user_prompt="", **kw):
        sp = system_prompt or ""
        # Answerability gate always gets YES so the relevance scorer is reached.
        if self._ANSWERABILITY_MARKER in sp:
            return "YES"
        # LLM reranker: return clips in natural 1,2 order so the relevance scorer
        # sees them in the same sequence as the canned score strings (e.g. "1,3"
        # means clip-1=vidA scores 1, clip-2=vidB scores 3).
        if self._RERANKER_MARKER in sp:
            return "1,2"
        # Relevance gate — wrap CSV scores as JSON when JSON schema path active.
        if kw.get("response_format"):
            raw = str(self.reply).strip()
            try:
                scores = [int(t) for t in raw.replace(" ", "").split(",") if t]
            except ValueError:
                scores = []
            import json

            return json.dumps({"scores": scores})
        return self.reply


def _pipeline(**kw):
    from services.first_person_pipeline import FirstPersonPipeline

    store = MagicMock()
    store.collection = "first_person_v1"
    redis = MagicMock()
    redis.get.return_value = None
    return FirstPersonPipeline(store=store, redis_client=redis, calibration_profile=None, **kw)


def _run_fp(scores_reply):
    with (
        patch(
            "services.first_person_pipeline.is_youtube_video_available",
            return_value=True,
        ),
        # Disable compound-question decomposition: this path invokes the scorer
        # once per facet with a single candidate, making a 2-score reply ("1,3")
        # truncate to [1] and always fall below the minimum. These tests exercise
        # the per-request relevance scorer, not compound-question handling.
        patch.object(
            settings,
            "first_person_facet_split_enabled",
            False,
        ),
        # Disable LLM reranker so the scorer receives clips in the natural
        # retrieval order and the score-to-clip mapping stays deterministic.
        patch.object(
            settings,
            "first_person_llm_rerank_enabled",
            False,
        ),
        # Disable speculative parallelism: in speculative mode the cascade scorer
        # calls each candidate clip individually, so a 2-score reply ("1,3") gets
        # truncated to [1] per call, always falling below the minimum. The non-
        # speculative path batches all candidates in one scorer call, matching the
        # per-clip score strings these tests exercise.
        patch.object(
            settings,
            "first_person_speculative_parallelism_enabled",
            False,
        ),
    ):
        pipe = _pipeline(llm_service=_SyncLLM(scores_reply))
        pipe._store.search_hybrid.return_value = [
            _clip(_GOOD_A, "vidA", [1.0, 0.0]),
            _clip(_GOOD_B, "vidB", [0.9, 0.1]),
        ]
        return pipe.execute(query="What is stillness?", query_dense_vector=[1.0, 0.0])


# ---------------------------------------------------------------- RP-C3 ---


@pytest.mark.asyncio
async def test_distress_preemption_increments_distress_counter():
    """One mechanical (no-LLM) distress turn shows the DISTRESS_DETECTIONS counter at +1."""
    from app.pipeline.stages.distress_stage import DistressStage
    from services.serene_mind_engine import DistressAssessment, DistressLevel

    before = metrics_mod.DISTRESS_DETECTIONS.labels(level="CRISIS")._value.get()
    assessment = DistressAssessment(level=DistressLevel.CRISIS, confidence=0.9)
    ctx = MagicMock(trace_id="rp-c3", start_time=0.0, is_indic=False, container=None)
    await DistressStage._crisis_preemption_result(ctx, assessment)
    after = metrics_mod.DISTRESS_DETECTIONS.labels(level="CRISIS")._value.get()
    assert after - before == 1


@pytest.mark.asyncio
async def test_kill_switch_increments_distress_counter_with_level_only_label(monkeypatch):
    """Kill-switch trip counts too, with a bounded level-only label (no text/ids)."""
    from app.pipeline.stages.kill_switch_stage import KillSwitchStage

    monkeypatch.setattr(settings, "generation_kill_switch_enabled", True)
    before = metrics_mod.DISTRESS_DETECTIONS.labels(level="KILL_SWITCH")._value.get()
    ctx = MagicMock(preferred_lang="en", trace_id="rp-c3-ks", start_time=0.0)
    await KillSwitchStage().run(ctx)
    after = metrics_mod.DISTRESS_DETECTIONS.labels(level="KILL_SWITCH")._value.get()
    assert after - before == 1


# ---------------------------------------------------------------- RP-C6 ---


def test_abstain_reasons_are_a_fixed_bounded_set():
    assert metrics_mod.FIRST_PERSON_ABSTAIN_REASONS == frozenset(
        {
            "none",
            "answerability_withheld",
            "relevance_below_min",
            "relevance_indeterminate",
            "no_verified_clips",
            "topic_blocked",
            # 2026-10-22 (B4): the legacy store pointed at an fp-context
            # collection, so the path served nothing. Deliberate vocabulary
            # change, not a drive-by.
            "serving_contract_violation",
        }
    )


@pytest.mark.relevance_real
def test_broken_scorer_counts_relevance_indeterminate_reason():
    """Forced scorer failure is indistinguishable today; it must count as indeterminate."""
    before = metrics_mod.FIRST_PERSON_REQUESTS_TOTAL.labels(
        status="abstained", reason="relevance_indeterminate"
    )._value.get()
    res = _run_fp("looks fine")
    assert res.status == "abstained"
    assert res.answerability == "relevance_indeterminate"
    assert res.abstain_reason == "relevance_indeterminate"
    after = metrics_mod.FIRST_PERSON_REQUESTS_TOTAL.labels(
        status="abstained", reason="relevance_indeterminate"
    )._value.get()
    assert after - before == 1


@pytest.mark.relevance_real
def test_below_min_counts_relevance_below_min_reason():
    before = metrics_mod.FIRST_PERSON_REQUESTS_TOTAL.labels(
        status="abstained", reason="relevance_below_min"
    )._value.get()
    res = _run_fp("1,0")
    assert res.status == "abstained"
    assert res.answerability == "relevance_below_min"
    assert res.abstain_reason == "relevance_below_min"
    after = metrics_mod.FIRST_PERSON_REQUESTS_TOTAL.labels(
        status="abstained", reason="relevance_below_min"
    )._value.get()
    assert after - before == 1


# --------------------------------------------------------------- RP-C10 ---


@pytest.mark.relevance_real
def test_relevance_score_histogram_observes_chosen_score():
    def _count():
        for fam in metrics_mod.FIRST_PERSON_RELEVANCE_SCORE.collect():
            for s in fam.samples:
                if s.name.endswith("_count"):
                    return s.value
        raise AssertionError("no _count sample on the relevance histogram")

    before_sum = metrics_mod.FIRST_PERSON_RELEVANCE_SCORE._sum.get()
    before_count = _count()
    res = _run_fp("1,3")
    assert res.status == "weak_match"
    assert res.citations[0]["video_id"] == "vidB"
    assert _count() - before_count == 1
    assert metrics_mod.FIRST_PERSON_RELEVANCE_SCORE._sum.get() - before_sum == 3


@pytest.mark.relevance_real
def test_token_counter_splits_answered_vs_abstained():
    before_answered = metrics_mod.FIRST_PERSON_LLM_TOKENS_TOTAL.labels(
        outcome="answered"
    )._value.get()
    before_abstained = metrics_mod.FIRST_PERSON_LLM_TOKENS_TOTAL.labels(
        outcome="abstained"
    )._value.get()
    _run_fp("1,3")  # served -> answered
    _run_fp("1,0")  # below min -> abstained
    answered_delta = (
        metrics_mod.FIRST_PERSON_LLM_TOKENS_TOTAL.labels(outcome="answered")._value.get()
        - before_answered
    )
    abstained_delta = (
        metrics_mod.FIRST_PERSON_LLM_TOKENS_TOTAL.labels(outcome="abstained")._value.get()
        - before_abstained
    )
    assert answered_delta > 0
    assert abstained_delta > 0


# ---------------------------------------------------------------- RP-A5 ---


def _fresh_key():
    return _pipeline()._get_exact_cache_key("what is stillness?")


def test_policy_fingerprint_covers_the_json_scorer_prompt(monkeypatch):
    """The Haiku scorer runs the JSON prompt + schema; editing either must
    re-key the exact cache, or answers scored under the old rubric replay."""
    import services.first_person_pipeline as fpp

    base = _fresh_key()
    monkeypatch.setattr(
        fpp, "_RELEVANCE_JSON_SYSTEM_PROMPT", fpp._RELEVANCE_JSON_SYSTEM_PROMPT + " stricter"
    )
    assert _fresh_key() != base
    monkeypatch.undo()
    assert _fresh_key() == base


def test_policy_fingerprint_scopes_cache_key(monkeypatch, tmp_path):
    """Changing each serving-policy setting changes the key; restoring restores it."""
    base = _fresh_key()
    allow = tmp_path / "allow.json"
    allow.write_text(json.dumps({"approved": ["vidA"]}), encoding="utf-8")

    cases = [
        # Toggle to a value that differs from the *env-resolved* base, not from
        # the declared default: the local `backend/.env` sets this to 2, so a
        # literal 2 would be a no-op here and the assertion below would fail
        # for an env reason rather than a fingerprint bug.
        ("first_person_relevance_min_score", settings.first_person_relevance_min_score + 1),
        ("first_person_relevance_model", "other/model"),
        ("first_person_relevance_gate_enabled", False),
        ("first_person_answerability_check_enabled", False),
        ("first_person_boundary_guard_enabled", True),
        ("first_person_content_quality_gate_enabled", False),
        ("first_person_standalone_gate_enabled", False),
        ("first_person_llm_rerank_enabled", False),
        ("first_person_serve_weak_match", False),
        ("first_person_editorial_rewrite_enabled", True),
        # 2026-10-20: the default is now retrieval_only, so toggle to a
        # *different* declared mode — toggling to the default value does not
        # change the key, and the assertion would pass/fail vacuously.
        ("first_person_mode", "disabled"),
        ("first_person_quality_allowlist_path", str(allow)),
        # Phase-D context harness: entered into the fingerprint BEFORE wiring, so
        # flipping any of them re-keys the exact cache instead of replaying a
        # pre-harness answer from the 24 h TTL.
        ("first_person_context_harness_enabled", True),
        ("first_person_context_max_spans", settings.first_person_context_max_spans + 1),
        ("first_person_context_selector_enabled", True),
    ]
    for name, toggled in cases:
        with monkeypatch.context() as m:
            m.setattr(settings, name, toggled)
            changed = _fresh_key()
            assert changed != base, f"{name} did not change the exact-cache key"
        assert _fresh_key() == base, f"{name} did not restore the exact-cache key"


# ---------------------------------------------------------------- RP-A9 ---


def test_llm_calls_per_request_constant_is_three():
    from app.config import LLM_CALLS_PER_REQUEST

    assert LLM_CALLS_PER_REQUEST == 3


def test_pool_must_cover_concurrent_fanout():
    from pydantic import ValidationError

    from app.config import Settings

    # The provider clients size their pool from http_max_connections, so that
    # is the setting the fan-out check guards (not http_pool_max_connections).
    # Fan-out covers direct requests AND queued jobs (queue_concurrency).
    with pytest.raises(ValidationError, match="http_max_connections"):
        Settings(max_concurrent_chat=12, http_max_connections=32)


def test_defaults_satisfy_pool_fanout():
    from app.config import LLM_CALLS_PER_REQUEST, Settings

    s = Settings()
    assert (
        s.http_max_connections
        >= (s.max_concurrent_chat + s.queue_concurrency) * LLM_CALLS_PER_REQUEST
    )


def test_cache_key_reuses_request_allowlist_state(monkeypatch, tmp_path):
    """One getmtime per request, not per key computation: passing an explicit
    allow_state must never touch the filesystem, and lookup/write keys built
    from it must be identical."""
    import os

    calls: list[str] = []
    real_getmtime = os.path.getmtime

    def _counting_getmtime(path):
        calls.append(str(path))
        return real_getmtime(path)

    monkeypatch.setattr(os.path, "getmtime", _counting_getmtime)
    allow = tmp_path / "allow.json"
    allow.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(settings, "first_person_quality_allowlist_path", str(allow))
    pipe = _pipeline()
    k1 = pipe._get_exact_cache_key("what is stillness?", allow_state="off")
    k2 = pipe._get_exact_cache_key("what is stillness?", allow_state="off")
    assert k1 == k2
    assert calls == [], "explicit allow_state must not stat the filesystem"
    pipe._get_exact_cache_key("what is stillness?")
    assert len(calls) == 1, "omitted allow_state recomputes exactly once"


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
