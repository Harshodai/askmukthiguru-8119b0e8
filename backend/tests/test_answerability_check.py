"""Phase 2 answerability gate (plan REVISION 2026-09-30).

Owner decision under test: an LLM classifies the QUESTION only (output exactly
YES/NO, never answers it) before ``is_direct=True`` is committed; strict parse
(strip -> casefold -> exact token); NO / indeterminate / missing service all
serve the existing honest abstention (zero citations).

Every test here carries ``answerability_real`` so the suite-wide YES stub in
tests/conftest.py does NOT apply — these tests exercise the real
``_answerability_check`` and its wire point in ``FirstPersonPipeline.execute``.
"""

import asyncio
import hashlib
import unicodedata

import pytest

from app.config import settings
from services.first_person_pipeline import (
    _ANSWERABILITY_SYSTEM_PROMPT,
    FirstPersonPipeline,
    _answerability_check,
)

pytestmark = pytest.mark.answerability_real


@pytest.fixture(autouse=True)
def _disable_speculative_parallelism(monkeypatch):
    """Force non-speculative path so the conftest _relevance_gate_stub applies.

    When speculative_parallelism_enabled=True, the pipeline uses asyncio.gather
    and does per-clip JSON scoring through the same llm_service stub. The stubs
    in this file return plain strings (e.g. "YES") that are invalid JSON for the
    response_format scorer path, which drives the score to 0 → relevance_below_min
    → abstained — not what these tests measure. The non-speculative path uses the
    conftest-stubbed _relevance_select (always index 0) instead, which is correct.
    """
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", False)


GOOD_TEXT = (
    "Suffering arises from resistance to what is. The moment you stop resisting, "
    "something shifts within you — not an escape, but a recognition of the truth."
)
GOOD_HASH = hashlib.sha256(GOOD_TEXT.encode("utf-8")).hexdigest()

VALID_PROFILE = {
    "threshold": 0.5,
    "score_kind": "dense_cosine",
    "n": 100,
    "ucb_risk": 0.01,
    "target_risk": 0.01,
    "collection": "first_person_v1",
    "fitted_at": "2026-09-24",
}

HONEST_ABSTENTION_TEXT = "No verified first-person discourse found for this question."


def _clip(**overrides):
    base = {
        "point_id": "p1",
        "video_id": "vid_abc",
        "start_ms": 65000,
        "end_ms": 75000,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "transcript_hash": GOOD_HASH,
        "verbatim_text": GOOD_TEXT,
        "passage_dense": [1.0, 0.0],
        "source_url": "https://youtube.com/watch?v=vid_abc",
        "caption_status": "auto_transcript",
    }
    base.update(overrides)
    return base


class _StubLLM:
    """Async generate() stub recording every call's prompts."""

    def __init__(self, reply="YES", raise_exc=None, sleep_s=0.0):
        self.reply = reply
        self.raise_exc = raise_exc
        self.sleep_s = sleep_s
        self.calls = []

    async def generate(self, system_prompt="", user_prompt="", **kwargs):
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.sleep_s:
            await asyncio.sleep(self.sleep_s)
        return self.reply


class _SyncStubLLM:
    """generate() returning a plain string (the rerank call style)."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def generate(self, system_prompt="", user_prompt="", **kwargs):
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        return self.reply


@pytest.fixture
def mock_store():
    from unittest.mock import MagicMock

    store = MagicMock()
    store.collection = "first_person_v1"
    return store


@pytest.fixture
def mock_redis():
    from unittest.mock import MagicMock

    redis = MagicMock()
    redis.get.return_value = None
    return redis


def _pipeline(mock_store, mock_redis, llm_service):
    return FirstPersonPipeline(
        store=mock_store,
        redis_client=mock_redis,
        calibration_profile=VALID_PROFILE,
        llm_service=llm_service,
    )


def _direct_setup(mock_store):
    """One clip at cosine 1.0 against query [1.0, 0.0] -> is_direct=True."""
    mock_store.search_hybrid.return_value = [_clip(passage_dense=[1.0, 0.0])]


# ---------------------------------------------------------------------------
# Strict parse (function level)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("YES", True),
        ("yes", True),
        ("  Yes  ", True),
        ("NO", False),
        ("no", False),
        ("\nNo\n", False),
        # strict parse: anything that is not exactly the token is indeterminate
        ("YES, because it is a core teaching", None),
        # trailing sentence punctuation alone is still a bare verdict (2026-10-15:
        # the fast model answers "YES." about 1 time in 9)
        ("yes.", True),
        ("No.", False),
        ("YES\nno", None),
        ("2,1,3", None),
        ("", None),
        # provider graceful-degradation canned string (AGENTS.md invariant #2)
        ("I'm currently experiencing a temporary connection issue with the provider.", None),
    ],
)
def test_strict_parse(reply, expected):
    assert _answerability_check("What is suffering?", _StubLLM(reply)) is expected


def test_no_llm_service_is_indeterminate():
    assert _answerability_check("What is suffering?", None) is None


def test_service_without_generate_is_indeterminate():
    assert _answerability_check("What is suffering?", object()) is None


def test_sync_generate_style_is_supported():
    assert _answerability_check("q", _SyncStubLLM("YES")) is True
    assert _answerability_check("q", _SyncStubLLM("NO")) is False


def test_timeout_is_indeterminate(monkeypatch):
    """A generate() slower than the budget fails toward abstention."""
    import services.first_person_pipeline as fpp

    monkeypatch.setattr(fpp, "_ANSWERABILITY_TIMEOUT_S", 0.05)
    slow = _StubLLM(reply="YES", sleep_s=1.0)
    assert _answerability_check("q", slow) is None


def test_provider_exception_is_indeterminate():
    boom = _StubLLM(raise_exc=RuntimeError("provider exploded"))
    assert _answerability_check("q", boom) is None


def test_provider_refusal_is_logged_distinctly_from_outage(caplog):
    """Review P3-4: a refusal lands indeterminate like an outage, but the log
    must tell them apart (metric reason is answerability_withheld either way)."""
    import logging

    from services.openrouter_service import ProviderRefusalError

    refused = _StubLLM(raise_exc=ProviderRefusalError("refused"))
    with caplog.at_level(logging.INFO):
        assert _answerability_check("q", refused) is None
    assert any("refused by provider" in r.message for r in caplog.records)
    assert not any("timeout/error" in r.message for r in caplog.records)


def test_persistent_gate_loop_is_created_once_and_reused():
    """2026-10-03 regression: per-call asyncio.run() killed shared Redis state
    (limiter + budget ledger) on every call after the first — 111/141
    validation verdicts were plumbing failures, not judgment. The process must
    keep ONE gate loop for its lifetime."""
    import services.first_person_pipeline as fpp

    loop_a = fpp._persistent_gate_loop()
    loop_b = fpp._persistent_gate_loop()
    assert loop_a is loop_b
    assert not loop_a.is_closed()


def test_consecutive_checks_all_get_real_verdicts():
    """Two back-to-back checks must both return real verdicts (no
    event-loop-closed bleed-through between calls)."""
    first = _answerability_check("q", _StubLLM("YES"))
    second = _answerability_check("q", _StubLLM("NO"))
    third = _answerability_check("q", _SyncStubLLM("YES"))
    assert (first, second, third) == (True, False, True)


def test_request_loop_is_honoured_when_provided():
    """Prod wiring: app/api/first_person.py captures the request loop and the
    gate schedules onto it via run_coroutine_threadsafe."""
    import threading

    import services.first_person_pipeline as fpp

    loop = asyncio.new_event_loop()
    ready = threading.Event()
    stop = threading.Event()

    def _run():
        asyncio.set_event_loop(loop)
        loop.call_soon(ready.set)
        loop.run_forever()
        stop.set()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    ready.wait(timeout=2.0)
    try:
        assert _answerability_check("q", _StubLLM("YES"), request_loop=loop) is True
        assert _answerability_check("q", _SyncStubLLM("NO"), request_loop=loop) is False
    finally:
        loop.call_soon_threadsafe(loop.stop)
        stop.wait(timeout=2.0)
        loop.close()
    assert fpp._persistent_gate_loop() is not loop


def test_user_is_raw_query_and_system_demands_single_token():
    llm = _StubLLM("YES")
    query = "What causes suffering?"  # raw seeker words, no wrapper, no translation
    assert _answerability_check(query, llm) is True
    assert llm.calls[0]["user_prompt"] == query
    assert "YES or NO" in llm.calls[0]["system_prompt"]
    assert "QUESTION ONLY" in llm.calls[0]["system_prompt"]
    # out-of-scope vocabulary is the Step 1b topic-rail vocabulary
    assert "cryptocurrency" in _ANSWERABILITY_SYSTEM_PROMPT
    assert "prompt_injection" in _ANSWERABILITY_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Wire point (execute level)
# ---------------------------------------------------------------------------


def test_yes_verdict_serves_direct(mock_store, mock_redis, monkeypatch):
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    _direct_setup(mock_store)
    llm = _StubLLM("YES")
    res = _pipeline(mock_store, mock_redis, llm).execute(
        query="What causes suffering?", query_dense_vector=[1.0, 0.0]
    )

    assert res.status == "success"
    assert res.is_direct_answer is True
    assert res.answerability == "yes"
    assert len(res.citations) >= 1
    # 2026-10-20: retrieval_only is the default again (config.py), so the gate's
    # YES/NO call is the ONLY LLM call — QuoteWeaver takes its deterministic
    # clip-only branch. Hybrid, an explicit opt-in, adds a scaffold call; that
    # path is covered by test_quote_weaver_scaffold_only.py.
    assert len(llm.calls) == 1


def test_no_verdict_abstains_with_zero_citations(mock_store, mock_redis):
    _direct_setup(mock_store)
    llm = _StubLLM("NO")
    res = _pipeline(mock_store, mock_redis, llm).execute(
        query="What is the capital of France?", query_dense_vector=[1.0, 0.0]
    )

    assert res.status == "abstained"
    assert res.is_direct_answer is False
    assert res.citations == []
    assert res.answerability == "no"
    assert res.answer_text == HONEST_ABSTENTION_TEXT
    # an out-of-domain verdict is never cached as an answer
    mock_store.search_hybrid.assert_called_once()


def test_no_profile_weak_match_is_also_gated(mock_store, mock_redis):
    """Live 2026-10-11: with no calibration profile every answer is weak_match, and
    out-of-corpus questions used to be served a teacher quote labelled 'Related'."""
    _direct_setup(mock_store)
    llm = _StubLLM("NO")
    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=None, llm_service=llm
    )
    res = pipeline.execute(query="What is the capital of France?", query_dense_vector=[1.0, 0.0])

    assert res.status == "abstained"
    assert res.citations == []
    assert res.answerability == "no"
    assert res.answer_text == HONEST_ABSTENTION_TEXT


def test_no_profile_weak_match_still_served_when_in_domain(mock_store, mock_redis):
    _direct_setup(mock_store)
    pipeline = FirstPersonPipeline(
        store=mock_store,
        redis_client=mock_redis,
        calibration_profile=None,
        llm_service=_StubLLM("YES"),
    )
    res = pipeline.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0])

    assert res.status == "weak_match"
    assert res.is_direct_answer is False
    assert len(res.citations) == 1


@pytest.mark.parametrize(
    "llm",
    [
        _StubLLM("YES, because suffering is resistance"),  # unparseable
        _StubLLM(raise_exc=RuntimeError("provider exploded")),  # exception
    ],
    ids=["unparseable", "exception"],
)
def test_indeterminate_verdict_abstains(mock_store, mock_redis, llm):
    _direct_setup(mock_store)
    res = _pipeline(mock_store, mock_redis, llm).execute(
        query="What causes suffering?", query_dense_vector=[1.0, 0.0]
    )

    assert res.status == "abstained"
    assert res.citations == []
    assert res.answerability == "indeterminate"
    assert res.answer_text == HONEST_ABSTENTION_TEXT


def test_missing_llm_service_abstains_under_flag_on(mock_store, mock_redis):
    """No service = indeterminate = abstain (fail-toward-honesty), never direct."""
    _direct_setup(mock_store)
    res = _pipeline(mock_store, mock_redis, None).execute(
        query="What causes suffering?", query_dense_vector=[1.0, 0.0]
    )

    assert res.status == "abstained"
    assert res.is_direct_answer is False
    assert res.citations == []
    assert res.answerability == "indeterminate"


def test_flag_off_is_exact_pre_change_behavior(mock_store, mock_redis, monkeypatch):
    """Kill-switch: the gate never runs (answerability=None), so a "NO" stub
    cannot force abstention. 2026-10-20: retrieval_only is the default, so the
    weaver makes NO LLM call either (deterministic clip-only); pin the mode so
    the assertion does not depend on a developer's env."""
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", False)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    _direct_setup(mock_store)
    llm = _StubLLM("NO")  # would abstain if the gate ran at all
    res = _pipeline(mock_store, mock_redis, llm).execute(
        query="What causes suffering?", query_dense_vector=[1.0, 0.0]
    )

    assert res.status == "success"
    assert res.is_direct_answer is True
    assert res.answerability is None
    assert llm.calls == []


def _legacy_cache_key(pipeline, query, teacher_id=None, language="en"):
    """The exact cache key formula as it was before the gate (flag off), accounting for D2 language."""
    norm = unicodedata.normalize("NFKC", query).strip().lower()
    t_id = (teacher_id or "both").strip().lower()
    lang = (language or "en").strip().lower()
    fitted_at = (pipeline._profile or {}).get("fitted_at") or (pipeline._profile or {}).get(
        "calibrated_at", "none"
    )
    rerank = "rerank" if pipeline._rerank_fn else "fusion"
    digest = hashlib.sha256(
        f"{norm}:{t_id}:{lang}:{pipeline._store.collection}:{fitted_at}:{rerank}".encode()
    ).hexdigest()
    return f"cache:first_person_exact:{lang}:{digest}"


def test_cache_key_is_scoped_by_flag_not_byte_identical(mock_store, mock_redis, monkeypatch):
    # RP-A5 (2026-10-13) supersedes the old byte-parity: the serving-policy
    # fingerprint is always part of the key now, so even the flag-off key no
    # longer equals the pre-gate formula (a stale pre-policy entry just misses).
    # What still holds: the flag itself scopes the key — flipping it on can
    # never serve a flag-off cached direct answer.
    pipeline = _pipeline(mock_store, mock_redis, _StubLLM("YES"))
    gated_key = pipeline._get_exact_cache_key("What causes suffering?")

    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", False)
    assert pipeline._get_exact_cache_key("What causes suffering?") != _legacy_cache_key(
        pipeline, "What causes suffering?"
    )
    # ...and flipping the flag on cannot serve a pre-gate cached direct answer
    assert gated_key != pipeline._get_exact_cache_key("What causes suffering?")


def test_crisis_precheck_short_circuits_before_gate(mock_store, mock_redis):
    """Safety order: distress pre-emption never spends an LLM call."""
    llm = _StubLLM("YES")
    pipeline = _pipeline(mock_store, mock_redis, llm)
    res = pipeline.execute(query="I want to kill myself today", query_dense_vector=[1.0, 0.0])

    assert res.status == "crisis_redirect"
    assert res.citations == []
    assert res.answerability is None
    assert llm.calls == []
    mock_store.search_hybrid.assert_not_called()


def test_topic_rail_blocks_before_gate(mock_store, mock_redis):
    """Step 1b topic rail also runs before the gate — no LLM call for blocked topics."""
    llm = _StubLLM("YES")
    pipeline = _pipeline(mock_store, mock_redis, llm)
    res = pipeline.execute(
        query="How do I invest in cryptocurrency for quick returns?",
        query_dense_vector=[1.0, 0.0],
    )

    assert res.status in ("abstained", "crisis_redirect")
    assert res.citations == []
    assert res.answerability is None
    assert llm.calls == []
    mock_store.search_hybrid.assert_not_called()


def test_gate_also_runs_for_weak_match_candidates(mock_store, mock_redis):
    """Reversed 2026-10-11: weak_match candidates are gated too (one 1-token call).
    The old 'never spend an LLM call below threshold' behaviour let out-of-corpus
    questions be served a teacher quote labelled 'Related, not a direct answer'."""
    mock_store.search_hybrid.return_value = [_clip(passage_dense=[0.0, 1.0])]  # cosine 0.0
    llm = _StubLLM("YES")
    res = _pipeline(mock_store, mock_redis, llm).execute(
        query="What causes suffering?", query_dense_vector=[1.0, 0.0]
    )

    assert res.status == "weak_match"
    assert res.answerability == "yes"
    assert len(llm.calls) == 1


def test_all_first_person_llm_calls_share_one_stable_loop():
    """Live 2026-10-11: rerank/weaver used asyncio.run() per call, poisoning shared
    provider clients so the gate failed with 'Event loop is closed' (16/27 on-topic
    questions abstained). Every sync LLM call must land on the SAME loop."""
    from services.first_person_pipeline import remember_request_loop, run_llm_coroutine
    from services.quote_weaver import _run_sync

    remember_request_loop(None)

    async def _loop_id():
        return id(asyncio.get_running_loop())

    gate_a = run_llm_coroutine(_loop_id, 2.0)
    gate_b = run_llm_coroutine(_loop_id, 2.0)
    weaver = _run_sync(_loop_id, timeout=2.0)

    assert gate_a == gate_b == weaver


def test_gate_prefers_the_fast_classify_model():
    """2026-10-15: the gate must not run on the slow generation model (6 s budget)."""

    class _Both:
        def __init__(self):
            self.used = None

        async def generate(self, **kw):
            self.used = "generate"
            return "YES"

        async def _generate_fast(self, **kw):
            self.used = "fast"
            return "YES"

    svc = _Both()
    assert _answerability_check("What is suffering?", svc) is True
    assert svc.used == "fast"


def test_prompt_keeps_safety_adjacent_topics_out_of_scope_and_conflict_in_scope():
    """2026-10-16: widening to interpersonal conflict must not re-admit abuse, harassment or addiction."""
    from services.first_person_pipeline import _ANSWERABILITY_SYSTEM_PROMPT as p

    for needle in (
        "abuse, coercive control or violence",
        "harassment",
        "drinking, drug, gambling or eating problem",
        "self-injury",
        "whether to divorce or quit",
        "conflict with a partner",
        "difficult boss",
    ):
        assert needle in p, needle
