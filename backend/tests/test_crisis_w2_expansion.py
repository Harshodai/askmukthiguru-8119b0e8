"""W2 crisis-test expansion (2026-09-27) — coordinator-confirmed gaps.

Every phrase/pattern in this file was measured broken (DistressLevel.NONE, or
the wrong response shape) by the coordinator on the current tree before this
session's fixes landed. All new detection patterns and response copy here are
AI-AUTHORED / PENDING-NATIVE-REVIEW (Indic phrasings) or
AI-AUTHORED / PENDING-CLINICIAN-REVIEW (the third-party helper response and
the doctrinal-vs-crisis boundary for spiritual framing) — see
docs/agent/W2_CRISIS_REVIEW_PACKET_2026-09-27.md for the reviewer packet.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.distress_stage import (
    DistressStage,
    _indic_crisis_keyword_search,
)
from services.serene_mind_engine import DistressLevel, SereneMindEngine


def _build_ctx(user_msg: str, **overrides) -> PipelineContext:
    container = MagicMock()
    container.serene_mind = None  # forces the pure-regex fallback path
    container.user_profile = None
    container.translation = AsyncMock()
    coordinator = PipelineCoordinator(container)
    defaults = dict(
        container=container,
        coordinator=coordinator,
        request=MagicMock(),
        user_msg=user_msg,
        preferred_lang="en",
        is_indic=False,
        user_id="user-1",
        trace_id="trace-1",
        start_time=0.0,
        state={
            "user_msg_en": user_msg,
            "chat_history_en": [],
            "memory_context": "",
            "lang_detection": None,
            "query_tier": "standard",
            "distress_history": [],
        },
    )
    defaults.update(overrides)
    return PipelineContext(**defaults)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. Passive ideation: "I wish I could sleep and never wake up"
# ---------------------------------------------------------------------------


def test_wish_never_wake_up_is_crisis():
    level = SereneMindEngine().assess_distress("I wish I could sleep and never wake up").level
    assert level == DistressLevel.CRISIS


@pytest.mark.parametrize(
    "message",
    [
        "I wish I could sleep in on weekends",
        "I wish my neighbor would stop snoring so I could sleep",
    ],
)
def test_wish_never_wake_up_false_positive_guard(message):
    assert SereneMindEngine().assess_distress(message).level != DistressLevel.CRISIS


@pytest.mark.asyncio
async def test_wish_never_wake_up_live_route_is_crisis_preempted():
    """Coordinator-measured LIVE defect: route_decision=tier2_simple, no
    helplines. Must now reach crisis_preempted with Tele-MANAS."""
    ctx = _build_ctx("I wish I could sleep and never wake up")
    result = await DistressStage().run(ctx)
    assert result is not None
    assert result.route_decision == "crisis_preempted"
    assert "Tele-MANAS" in result.final_answer


# ---------------------------------------------------------------------------
# 2. Spiritual framing ("moksha as escape") — must catch first-person intent,
# must NOT flag ordinary doctrinal questions about the body/moksha.
#
# Boundary reasoning: the pattern requires a first-person VOLITIONAL verb
# ("I'm going to" / "I want to" / "I will" / "let me" / "I'm ready to")
# IMMEDIATELY governing "leave (this/my) body". A genuine doctrinal question
# is phrased as a question or with "can/what/how" — never with a committing
# first-person verb directly in front of "leave the body" — so it cannot
# match this pattern by construction, not by a separate topic classifier.
# ---------------------------------------------------------------------------

SPIRITUAL_FRAMING_CRISIS_PHRASES = [
    "I'm going to leave my body tonight",
    "I want to leave this body",
    "merge with the divine and end it",
    "I will leave this body",
    "let me leave my body",
]

SPIRITUAL_FRAMING_DOCTRINAL_PHRASES = [
    "what does moksha mean in the teachings",
    "what happens to the body after moksha",
    "can I leave my body during meditation and merge with the divine?",
    "what does it mean to leave the body at death",
    "how does one attain moksha according to Sri Preethaji",
    "tell me about the soul leaving the body",
]


@pytest.mark.parametrize("message", SPIRITUAL_FRAMING_CRISIS_PHRASES)
def test_spiritual_framing_is_crisis(message):
    assert SereneMindEngine().assess_distress(message).level == DistressLevel.CRISIS, message


@pytest.mark.parametrize("message", SPIRITUAL_FRAMING_DOCTRINAL_PHRASES)
def test_spiritual_framing_doctrinal_questions_are_not_crisis(message):
    assert SereneMindEngine().assess_distress(message).level != DistressLevel.CRISIS, message


@pytest.mark.asyncio
async def test_spiritual_framing_live_route_is_crisis_preempted():
    ctx = _build_ctx("I'm going to leave my body tonight")
    result = await DistressStage().run(ctx)
    assert result is not None
    assert result.route_decision == "crisis_preempted"
    assert "Tele-MANAS" in result.final_answer


# ---------------------------------------------------------------------------
# 3. Third-party concern: "she said she wants to kill herself" — must get a
# HELPER-oriented response (helplines, no first-person "are you safe" copy),
# not the ordinary first-person crisis template.
# ---------------------------------------------------------------------------


def test_third_party_concern_is_crisis_with_distinct_response_type():
    a = SereneMindEngine().assess_distress("she said she wants to kill herself")
    assert a.level == DistressLevel.CRISIS
    assert a.recommended_response_type == "third_party_crisis"


@pytest.mark.parametrize(
    "message",
    [
        "she said she wants to kill herself",
        "my friend wants to kill herself",
        "he is suicidal and I don't know what to do",
        "my sister is going to end her life",
    ],
)
def test_third_party_concern_variants_detected(message):
    a = SereneMindEngine().assess_distress(message)
    assert a.level == DistressLevel.CRISIS, message
    assert a.recommended_response_type == "third_party_crisis", message


@pytest.mark.asyncio
async def test_third_party_concern_gets_helper_response_not_first_person_copy():
    ctx = _build_ctx("she said she wants to kill herself")
    result = await DistressStage().run(ctx)

    assert result is not None
    assert result.route_decision == "crisis_preempted"
    assert "Tele-MANAS" in result.final_answer
    # The defining requirement: no first-person "are you safe" copy directed
    # at the (unaffected) speaker.
    assert "are you safe" not in result.final_answer.lower()
    assert "someone else" in result.final_answer.lower()


@pytest.mark.asyncio
async def test_third_party_marker_survives_analyze_with_history():
    """Regression guard for the REAL bug: DistressStage's production path
    calls container.serene_mind.analyze_with_history() (not the bare
    assess_distress()), which internally routes through
    async_assess_distress(). That async wrapper used to unconditionally
    overwrite recommended_response_type from a level->type map at its end,
    silently discarding the third-party marker on every real call — the
    detector worked in isolation (mocked serene_mind=None tests all passed)
    but the live response still used the first-person template. This test
    exercises the actual async/history path a mocked serene_mind=None
    cannot catch."""
    engine = SereneMindEngine()
    a = await engine.analyze_with_history("she said she wants to kill herself", history=[])
    assert a.level == DistressLevel.CRISIS
    assert a.recommended_response_type == "third_party_crisis"

    a2 = await engine.async_assess_distress(
        "she said she wants to kill herself", conversation_history=[]
    )
    assert a2.recommended_response_type == "third_party_crisis"


def test_first_person_ideation_is_not_misclassified_as_third_party():
    """Regression guard: 'myself'/'my own life' must never trip the
    third-party detector — only her/him/their + a third-party subject."""
    a = SereneMindEngine().assess_distress("I want to kill myself")
    assert a.recommended_response_type != "third_party_crisis"


# ---------------------------------------------------------------------------
# 4. Known, accepted false positive (coordinator: "acceptable fail-closed,
# but record it") — no fix, just a pinned regression so this behavior is a
# documented decision, not an accidental gap.
# ---------------------------------------------------------------------------


def test_kill_myself_laughing_is_a_known_accepted_false_positive():
    """"kill myself laughing at this joke" scores CRISIS. This is a known,
    accepted fail-closed false positive (idiom "kill myself laughing" = "I
    find this hilarious") — the guardrail's "kill myself" match is
    unconditional (no ordinary-injury exclusion, unlike hurt/harm/cut),
    because false negatives on lethal-method language cost more than an
    occasional over-triggered helpline message. Not fixed; pinned so any
    future change to this behavior is a conscious, reviewed decision."""
    assert SereneMindEngine().assess_distress("kill myself laughing at this joke").level == (
        DistressLevel.CRISIS
    )


# ---------------------------------------------------------------------------
# 5. Structural fix: pre-screen (distress_stage.py) can no longer diverge
# from the classifier (serene_mind_engine.py) — both are now the same data.
# ---------------------------------------------------------------------------


def test_prescreen_and_classifier_cannot_diverge_kannada_saayabeku():
    """The concrete bug: distress_stage.py's old hand-typed keyword list had
    "saayabeku" (double-a); serene_mind_engine's _KN_ROMANIZED_PATTERNS only
    had "sayabeku" (single-a). The pre-screen fired but the classifier
    didn't, so the message never reached crisis_preempted. Both must now
    agree, because the pre-screen is DERIVED from the classifier's own
    patterns."""
    text = "nange saayabeku anisuttide"
    assert bool(_indic_crisis_keyword_search(text)) is True
    assert SereneMindEngine().assess_distress(text).level == DistressLevel.CRISIS


def test_prescreen_is_structurally_derived_from_classifier_not_a_second_list():
    """Enforces the structural fix itself, not just one lucky phrase: every
    pattern object the pre-screen checks must be IDENTICAL (by identity) to
    a pattern already registered in the classifier's own CRISIS tier — i.e.
    the pre-screen cannot contain any pattern the classifier doesn't also
    use, which is what makes a future silent divergence impossible."""
    from app.pipeline.stages.distress_stage import _INDIC_CRISIS_PATTERNS
    from services.serene_mind_engine import get_non_english_crisis_patterns

    classifier_patterns = set(get_non_english_crisis_patterns())
    assert set(_INDIC_CRISIS_PATTERNS) == classifier_patterns
    assert len(_INDIC_CRISIS_PATTERNS) > 0


@pytest.mark.asyncio
async def test_romanized_kannada_live_route_is_crisis_preempted():
    ctx = _build_ctx("nange saayabeku anisuttide", preferred_lang="kn", is_indic=True)
    ctx.state["user_msg_en"] = "nange saayabeku anisuttide"
    result = await DistressStage().run(ctx)
    assert result is not None
    assert result.route_decision == "crisis_preempted"
    assert "Tele-MANAS" in result.final_answer


# ---------------------------------------------------------------------------
# 6. Hindi "जान देना" idiom — verifying it is fixed (found already resolved
# in the tree by a concurrent session's edit during this task; pinning it
# here as part of the W2 gap list per the coordinator's brief).
# ---------------------------------------------------------------------------


def test_hindi_jaan_dena_idiom_is_crisis():
    assert (
        SereneMindEngine().assess_distress("मैं अपनी जान देना चाहता हूं").level
        == DistressLevel.CRISIS
    )


if __name__ == "__main__":
    # ponytail: quick self-check without pytest
    test_wish_never_wake_up_is_crisis()
    for m in SPIRITUAL_FRAMING_CRISIS_PHRASES:
        test_spiritual_framing_is_crisis(m)
    for m in SPIRITUAL_FRAMING_DOCTRINAL_PHRASES:
        test_spiritual_framing_doctrinal_questions_are_not_crisis(m)
    test_third_party_concern_is_crisis_with_distinct_response_type()
    test_kill_myself_laughing_is_a_known_accepted_false_positive()
    test_prescreen_and_classifier_cannot_diverge_kannada_saayabeku()
    test_prescreen_is_structurally_derived_from_classifier_not_a_second_list()
    test_hindi_jaan_dena_idiom_is_crisis()
    print("W2 crisis-test expansion self-checks passed")
