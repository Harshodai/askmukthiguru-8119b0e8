"""Ticket A28 — follow-up behaviour on the verbatim (first-person) path.

Spec (the source of the measurements and the options): ``docs/FIRST_PERSON_FOLLOWUPS_SPEC.md``.

The deliverable for A28 is a *proposal*, so these tests pin **what the system
does today** so the owner's decision (and any later implementation) shows up as
a diff:

  * ``unit`` tests pin the deterministic machinery — the resolver heuristics
    (``rag/resolve_followup.py``), the bridge's retrieval rewrite
    (``app/pipeline/stages/first_person_bridge.py``) and the history → distress
    coupling (``app/pipeline/stages/distress_stage.py``). They always run.
  * ``integration`` tests pin the live API classes measured on 2026-10-19
    (cold follow-up, two-turn follow-up, language-switch follow-up, standalone
    control). They are opt-in (``A28_LIVE_PROBES=1``) because each run makes
    ~12 real chat turns, then skip when the stack or the benchmark key is absent.

Known non-determinism, deliberately NOT pinned: whether a *marginal* standalone
question is served a clip or abstains is decided by an LLM answerability
classifier. On 2026-10-19 ``"What is the Beautiful State?"`` served a
``weak_match`` clip at 08:45Z (``verdict=yes``) and abstained at 08:51Z
(``status=abstained reason=relevance_below_min``) on the *same* cold query. The
integration tests therefore assert routing/serving *classes* and never assert a
serve/abstain outcome for a marginal question.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.request
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.pipeline.stages import first_person_bridge as bridge_module
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.distress_stage import DistressStage
from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
from rag.resolve_followup import _get_last_user_message, _is_heuristic_followup
from services.serene_mind_engine import DistressLevel

# --------------------------------------------------------------------------
# Shared fixtures: the anchor turn used by every live probe, and the four
# follow-up strings from the ticket.
# --------------------------------------------------------------------------

ANCHOR_QUESTION = "What is the suffering state?"
# Deliberately the *shortened* anchor turn (first ~120 chars of the served clip).
# With the full 637-char answer as the assistant turn, the history-aware distress
# classifier rated ambiguous follow-ups MODERATE and handed them to the general
# graph; with this shortened text all four stayed first-person. The anchor text
# is a load-bearing input, which is why the integration tests pin structure, not
# the route flip (spec §2.1-3).
ANCHOR_HISTORY = [
    {"role": "user", "content": ANCHOR_QUESTION},
    {
        "role": "assistant",
        "content": (
            'Related, not a direct answer:  "There are only two states in which any '
            'human being on this planet lives..."'
        ),
    },
]

COLD_FOLLOWUPS = ["tell me more", "say it simpler", "can you explain that", "in Hindi please"]
TWO_TURN_FOLLOWUPS = ["tell me more", "say it simpler", "can you explain that", "in Hindi please"]
CONTROL_QUESTION = "What is the Beautiful State?"

STATIC_ABSTAIN_MARKER = "I don't have a verified verbatim teaching"


# ==========================================================================
# Unit — the resolver heuristic (the cold-vs-history distinction)
# ==========================================================================


def test_cold_followup_is_never_flagged_as_a_followup():
    """A follow-up with no history is not a follow-up.

    Breaks if ``_is_heuristic_followup`` stops returning early on empty history:
    the bridge would then rewrite the retrieval query against nothing (or raise
    on ``_get_last_user_message([])``), turning a cold follow-up into a
    different failure class than the measured static abstain.
    """
    for followup in COLD_FOLLOWUPS:
        assert _is_heuristic_followup(followup, []) is False, followup


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # Detected by phrase and/or referential rule.
        ("tell me more", True),
        ("tell me more about the Beautiful State", True),
        ("say it simpler", True),  # referential word "it", <= 8 words
        ("can you explain that", True),  # phrase "explain that" + "that"
        ("what does that mean", True),
        # NOT detected — the two measured gaps.
        ("in Hindi please", False),  # language directive: no phrase, no referential word
        (CONTROL_QUESTION, False),  # a standalone question is not a follow-up
    ],
)
def test_followup_classification_matrix_with_history(question, expected):
    """Pins the exact heuristic matrix the measured probe table depends on.

    Breaks for a real reason when the ruleset changes: adding a language-directive
    or simplification rule (spec Option D / Option C) flips ``"in Hindi please"``
    to ``True``; broadening the referential rule flips the ``CONTROL_QUESTION``
    row to ``True`` — which is the mis-rewrite the spec §2.1 calls harmful.
    """
    assert _is_heuristic_followup(question, ANCHOR_HISTORY) is expected


def test_last_user_message_selection_and_cap():
    """The rewrite anchors on the most recent *user* message, capped at 200 chars.

    Breaks if the selector returns the assistant turn (the bridge would anchor a
    follow-up on the previous answer text) or the 200-char cap is lifted (a long
    anchor would silently reshape the retrieval query).
    """
    history = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "answer"},
        {"role": "user", "content": "second question"},
    ]
    assert _get_last_user_message(history) == "second question"
    assert _get_last_user_message([]) == ""
    assert _get_last_user_message([{"role": "assistant", "content": "a"}]) == ""
    long_anchor = "x" * 500
    assert len(_get_last_user_message([{"role": "user", "content": long_anchor}])) == 200


# ==========================================================================
# Unit — the bridge's retrieval rewrite (mocked pipeline, no infra)
# ==========================================================================


def _container() -> MagicMock:
    container = MagicMock()
    container.embedding = AsyncMock()
    container.embedding.encode_single_full_async.return_value = {
        "dense": [0.0] * int(settings.embedding_dimension),
        "sparse": {},
    }
    container.serene_mind = None
    container.translation = None
    return container


def _ctx(container, *, msg: str, history: list) -> PipelineContext:
    return PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg=msg,
        preferred_lang="en",
        is_indic=False,
        trace_id="trace-a28-unit",
        start_time=time.time(),
        state={"user_msg_en": msg},
        chat_body_messages=history,
    )


@pytest.fixture(autouse=True)
def _bridge_gates(monkeypatch):
    """Bridge gates on; served results keep the weak-match opt-in."""
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    monkeypatch.setattr(settings, "first_person_distress_serve_clip_enabled", False)


@pytest.fixture
def fp_pipeline(monkeypatch):
    """Mocked FirstPersonPipeline — capture the retrieval query it receives."""
    pipeline = MagicMock()
    pipeline.execute = MagicMock(
        return_value=SimpleNamespace(
            answer_text="",
            citations=[],
            status="abstained",
            is_direct_answer=False,
            latency_ms=1.0,
            cached=False,
            error=None,
        )
    )
    monkeypatch.setattr(bridge_module, "_fp_pipeline", lambda container: pipeline)
    return pipeline


def _retrieval_query(pipeline) -> str:
    return pipeline.execute.call_args.kwargs["retrieval_query"]


@pytest.mark.asyncio
async def test_bridge_rewrites_an_anaphoric_followup_against_the_anchor(fp_pipeline):
    """Today's rewrite: ``"{last user message} — {follow-up}"`` (em dash).

    Breaks if the rewrite is removed (Option A) or made anchor-identity aware
    (Option B) — either is a real, deliberate change the owner must approve.
    """
    await FirstPersonBridgeStage().run(
        _ctx(_container(), msg="tell me more", history=ANCHOR_HISTORY)
    )
    assert _retrieval_query(fp_pipeline) == f"{ANCHOR_QUESTION} — tell me more"


@pytest.mark.asyncio
async def test_bridge_rewrite_ignores_a_language_directive(fp_pipeline):
    """``"in Hindi please"`` is *not* rewritten — the bridge cannot see a language request.

    Breaks when spec Option D's deterministic follow-up classifier lands and
    starts routing the language directive somewhere other than plain retrieval.
    """
    await FirstPersonBridgeStage().run(
        _ctx(_container(), msg="in Hindi please", history=ANCHOR_HISTORY)
    )
    assert _retrieval_query(fp_pipeline) == "in Hindi please"


@pytest.mark.asyncio
async def test_bridge_leaves_a_standalone_question_untouched(fp_pipeline):
    """A non-anaphoric second-turn question keeps its own text as the retrieval query.

    Breaks if the rewrite is broadened to every history-bearing turn: the
    standalone question would be force-joined to an unrelated anchor (the
    ``"What is the Beautiful State?"`` failure mode), silently changing which
    clip the verbatim gate is allowed to consider.
    """
    await FirstPersonBridgeStage().run(
        _ctx(_container(), msg=CONTROL_QUESTION, history=ANCHOR_HISTORY)
    )
    assert _retrieval_query(fp_pipeline) == CONTROL_QUESTION


# ==========================================================================
# Unit — the history → distress coupling that flips the two-turn route
# ==========================================================================


@pytest.mark.asyncio
async def test_distress_stage_forwards_chat_history_to_the_history_aware_classifier():
    """``DistressStage`` passes ``chat_history_en`` into ``analyze_with_history``.

    This coupling (distress_stage.py:492-493) is *why* a two-turn follow-up over a
    suffering anchor reaches MODERATE and is handed to the generating graph. It
    breaks if the history argument is dropped (no history-aware scoring) or the
    stage stops calling the history-aware entry point.
    """
    assessment = SimpleNamespace(level=DistressLevel.NONE, recommendations=[])
    serene = AsyncMock()
    serene.analyze_with_history = AsyncMock(return_value=assessment)
    ctx = SimpleNamespace(container=SimpleNamespace(serene_mind=serene))

    state = {"chat_history_en": ANCHOR_HISTORY}
    await DistressStage()._detect_distress(ctx, "tell me more", state)

    serene.analyze_with_history.assert_awaited_once()
    _, kwargs = serene.analyze_with_history.await_args
    # The history travels as a keyword argument with the message.
    assert kwargs["history"] == ANCHOR_HISTORY


# ==========================================================================
# Integration — the live API classes (skip when the stack/key is absent)
# ==========================================================================

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
_BASE_URL = os.environ.get("A28_BASE_URL", "http://localhost:8000").rstrip("/")
_CHAT_URL = f"{_BASE_URL}/api/chat"


def _benchmark_key() -> str | None:
    """Read the benchmark secret without ever printing it.

    ``backend/.env`` is the source of truth for a live local probe, and is read
    *first* on purpose: ``tests/conftest.py`` injects a synthetic
    ``BENCHMARK_SECRET`` into ``os.environ`` for unit fixtures, and sending that
    value to the real API is not recognised as a benchmark client — the probe
    then hits the shared 20 req/min limiter and every call 429s.
    ``A28_BENCHMARK_SECRET`` overrides either source.
    """
    override = os.environ.get("A28_BENCHMARK_SECRET")
    if override:
        return override
    env_path = _BACKEND_DIR / ".env"
    if env_path.exists():
        match = re.search(r"^BENCHMARK_SECRET=(.*)$", env_path.read_text(), re.M)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return os.environ.get("BENCHMARK_SECRET") or None


@pytest.fixture(scope="module")
def live_chat():
    """Skip the module's integration tests unless the local stack answers.

    ``/api/chat`` answers inline when there is capacity and queues a job (HTTP
    200, ``status=queued``) when chat slots are busy, so the helper polls
    ``poll_url`` until the job completes. The benchmark key exempts the probe
    from the rate limiter/quota but not from the queue.
    """

    # Opt-in, not merely "is the stack up". ``addopts`` runs the ``integration``
    # marker by default, so a reachability-only gate would make this file fire
    # ~10 live LLM turns (with 300 s polling) inside every ordinary unit run on
    # any developer machine that happens to have the stack running — minutes of
    # wall clock, real provider spend, and queue contention with whatever else is
    # being measured. The unit tests above already pin the machinery these probes
    # re-confirm; run these deliberately:
    #   A28_LIVE_PROBES=1 .venv/bin/pytest tests/test_first_person_followups_2026_10_19.py -m integration -q
    if os.environ.get("A28_LIVE_PROBES") != "1":
        pytest.skip("live follow-up probes are opt-in (set A28_LIVE_PROBES=1)")

    key = _benchmark_key()

    def _request(url: str, payload: dict | None = None) -> dict:
        """POST/GET with a short 429 backoff (``/api/chat`` is 20 req/min).

        Peer sessions share the limiter, so a persistent 429 is a *skip* (the
        stack is up but busy), never a retry storm: four attempts, 5s apart.
        """
        delay = 5.0
        for attempt in range(4):
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode() if payload is not None else None,
                headers={
                    "Content-Type": "application/json",
                    "X-Test-Key": key or "",
                    "Connection": "close",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=180) as response:  # nosec B310 -- configured live-test target
                    return json.loads(response.read().decode())
            except urllib.error.HTTPError as exc:
                if exc.code != 429 or attempt == 3:
                    raise
                time.sleep(delay)
        raise RuntimeError("unreachable")

    def _post(user_message: str, messages: list, language: str = "en") -> dict:
        body = {
            "user_message": user_message,
            "messages": messages,
            "language": language,
            "cache_bypass": True,
        }
        try:
            data = _request(_CHAT_URL, body)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                pytest.skip("chat endpoint rate-limited (429) — rerun when idle")
            raise
        poll_path = (
            data.get("poll_url") if str(data.get("status")) in {"queued", "processing"} else None
        )
        deadline = time.time() + 300
        while poll_path and time.time() < deadline:
            time.sleep(2.0)
            job = _request(_BASE_URL + poll_path)
            status = str(job.get("status") or "")
            if status == "completed":
                return job.get("result") or {}
            if status in {"failed", "cancelled"}:
                pytest.fail(f"live chat job {status}: {job.get('error')}")
        if poll_path:
            pytest.fail("live chat job did not complete within 300s")
        return data

    if not key:
        pytest.skip("BENCHMARK_SECRET not configured for live follow-up probes")
    try:
        _post("hello", [])
    except urllib.error.HTTPError as exc:
        pytest.skip(f"live chat stack rejected the probe (HTTP {exc.code})")
    except urllib.error.URLError as exc:
        pytest.skip(f"live chat stack unavailable: {exc}")
    return _post


def _route(data: dict) -> str:
    return str(data.get("route_decision") or "")


def _method(data: dict) -> str | None:
    return (data.get("verification") or {}).get("method")


@pytest.mark.integration
def test_cold_followup_class_stays_first_person_and_never_synthesises(live_chat):
    """Cold follow-up class: no anchor → honest first-person abstain, never the graph.

    Measured 2026-10-19: all four cold follow-ups returned
    ``first_person_abstain`` / ``first_person_no_match_abstain``, 0 citations,
    the 173-char static abstain. Breaks if the bridge starts routing a
    content-free follow-up to the generating graph, or if a follow-up is served
    a clip as a "direct" answer with no anchor.
    """
    for followup in COLD_FOLLOWUPS:
        data = live_chat(followup, [])
        route = _route(data)
        assert route.startswith("first_person"), (followup, route, data.get("response"))
        assert (data.get("verification") or {}).get("direct") is not True, followup
        citations = data.get("citations") or []
        if not citations:
            assert data.get("grounding_state") == "abstained", followup
            assert STATIC_ABSTAIN_MARKER in (data.get("response") or ""), followup


@pytest.mark.integration
def test_two_turn_followup_class_is_never_served_as_a_direct_answer(live_chat):
    """Two-turn follow-up class: history may change the *route*, never into a direct clip.

    Measured 2026-10-19 with the **real served anchor text**: ``tell me more`` /
    ``can you explain that`` / ``in Hindi please`` reached the general graph
    (``tier2_simple``) via a MODERATE distress rating on the history-aware
    classifier; ``say it simpler`` stayed first-person and abstained.

    That route flip is deliberately **not** pinned: re-measured 2026-10-19 with a
    shortened anchor text every follow-up stayed first-person
    (``first_person_abstain``, except ``tell me more`` → ``first_person_bridge``),
    i.e. the flip depends on the anchor text/classifier, not on the follow-up
    string. What is pinned is structural and stable: a follow-up is never served
    as ``direct``, a first-person abstain carries no citations, and a first-person
    serve keeps the verbatim-gate method. Breaks if a follow-up becomes a direct
    answer, invents citations while abstaining, or is served by a non-verbatim
    method.
    """
    allowed = {
        "first_person_abstain",
        "first_person_bridge",
        "tier2_simple",
        "standard",
        "deep",
    }
    for followup in TWO_TURN_FOLLOWUPS:
        data = live_chat(followup, ANCHOR_HISTORY)
        route = _route(data)
        assert route in allowed, (followup, route, data)
        assert (data.get("verification") or {}).get("direct") is not True, (followup, route)
        if route.startswith("first_person"):
            citations = data.get("citations") or []
            if not citations:
                assert data.get("grounding_state") == "abstained", (followup, route)
            else:
                # A first-person serve for a follow-up must keep the weak-match
                # label — never claim a follow-up is a direct answer.
                assert _method(data) == "first_person_verbatim_clip_gate", (followup, route)


@pytest.mark.integration
def test_language_switch_followup_class_returns_abstain_in_requested_language(live_chat):
    """``"in Hindi please"``: not recognised as a language transform; the graph abstains.

    Measured 2026-10-19: with ``language=hi`` the two-turn probe returned a
    112-char Hindi abstain; with ``language=en`` a 97-char English one. Neither
    served a clip. Breaks if a language-directive follow-up starts returning a
    translation of the anchor clip (which the verbatim invariant forbids) or
    stops honouring ``language`` on the abstain text.
    """
    for language, expected_marker in (("en", "cannot answer"), ("hi", "नहीं दे सकता")):
        data = live_chat("in Hindi please", ANCHOR_HISTORY, language=language)
        route = _route(data)
        assert route, (language, data)
        assert (data.get("verification") or {}).get("direct") is not True, language
        if route.startswith("first_person"):
            # Still acceptable: the localized static abstain. Never a clip.
            assert not (data.get("citations") or []), (language, data.get("response"))
        else:
            assert data.get("grounding_state") == "abstained", (language, data.get("response"))
            assert expected_marker in (data.get("response") or ""), (language, data.get("response"))


@pytest.mark.integration
def test_standalone_control_is_not_treated_as_a_followup_turn(live_chat):
    """Control class: a real question keeps normal routing cold and as a second turn.

    Measured 2026-10-19: a marginal question's serve/abstain is LLM-decided (it
    served at 08:45Z and abstained at 08:51Z cold), so this test asserts the
    *class* only — normal first-person or graph routing, no direct claim, and no
    fabricated citations when abstained. Breaks if the control question is ever
    force-rewritten into a follow-up (route/anchor contamination) or served as
    ``direct``.
    """
    for history in ([], ANCHOR_HISTORY):
        data = live_chat(CONTROL_QUESTION, history)
        route = _route(data)
        assert route, (history, data)
        assert (data.get("verification") or {}).get("direct") is not True, (history, route)
        if data.get("grounding_state") == "abstained":
            assert not (data.get("citations") or []), (history, data)
