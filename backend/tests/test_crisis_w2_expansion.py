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
#
# 2026-09-28 (owner-approved "escalate-only + re-tier"): RE-TIERED to SEVERE
# (a gentle check-in + helplines), not the full CRISIS "are you safe right
# now" copy — see serene_mind_engine.py's `_SEVERE_IDEATION_CHECKIN_MARKERS`.
# Superseding the earlier W2 assertion that this was CRISIS.
# ---------------------------------------------------------------------------


def test_wish_never_wake_up_is_severe_not_crisis():
    a = SereneMindEngine().assess_distress("I wish I could sleep and never wake up")
    assert a.level == DistressLevel.SEVERE
    assert a.level != DistressLevel.NONE  # never NONE, per owner's explicit rule
    assert a.recommended_response_type == "severe_ideation_checkin"


@pytest.mark.parametrize(
    "message",
    [
        "I wish I could sleep in on weekends",
        "I wish my neighbor would stop snoring so I could sleep",
    ],
)
def test_wish_never_wake_up_false_positive_guard(message):
    assert SereneMindEngine().assess_distress(message).level != DistressLevel.SEVERE
    assert SereneMindEngine().assess_distress(message).level != DistressLevel.CRISIS


@pytest.mark.asyncio
async def test_wish_never_wake_up_live_route_is_severe_checkin_with_helplines():
    """Coordinator-measured LIVE defect (2026-09-27): route_decision=tier2_simple,
    no helplines. Must now reach crisis_preempted (the stage that carries
    SEVERE/CRISIS both) with the SEVERE check-in copy and Tele-MANAS present,
    NOT the full "are you safe right now" CRISIS copy."""
    ctx = _build_ctx("I wish I could sleep and never wake up")
    result = await DistressStage().run(ctx)
    assert result is not None
    assert result.route_decision == "crisis_preempted"
    assert "Tele-MANAS" in result.final_answer
    assert "are you safe right now" not in result.final_answer.lower()


# ---------------------------------------------------------------------------
# 2. Spiritual framing ("moksha as escape") — must catch first-person intent,
# must NOT flag ordinary doctrinal questions about the body/moksha.
#
# 2026-09-28 (owner-approved re-tier): split by whether the phrase carries
# INTENT, A PLAN, A METHOD, or A TIMEFRAME (CRISIS) vs. ambiguous desire with
# none of those (SEVERE check-in). Boundary reasoning for BOTH tiers: a
# first-person VOLITIONAL verb must IMMEDIATELY govern "leave (this/my)
# body" — a genuine doctrinal question is phrased as a question or with
# "can/what/how", never with a committing first-person verb directly in
# front of "leave the body", so it cannot match either tier by construction.
# ---------------------------------------------------------------------------

SPIRITUAL_FRAMING_CRISIS_PHRASES = [
    "I'm going to leave my body tonight",
    "merge with the divine and end it",
    "I will leave this body",
    "I want to leave this body tonight",  # weaker modal + explicit timeframe -> still CRISIS
]

SPIRITUAL_FRAMING_SEVERE_PHRASES = [
    "I want to leave this body",
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
def test_spiritual_framing_with_intent_plan_or_timeframe_is_crisis(message):
    assert SereneMindEngine().assess_distress(message).level == DistressLevel.CRISIS, message


@pytest.mark.parametrize("message", SPIRITUAL_FRAMING_SEVERE_PHRASES)
def test_spiritual_framing_ambiguous_is_severe_checkin(message):
    a = SereneMindEngine().assess_distress(message)
    assert a.level == DistressLevel.SEVERE, message
    assert a.recommended_response_type == "severe_ideation_checkin", message


@pytest.mark.parametrize("message", SPIRITUAL_FRAMING_DOCTRINAL_PHRASES)
def test_spiritual_framing_doctrinal_questions_are_not_crisis(message):
    assert SereneMindEngine().assess_distress(message).level != DistressLevel.CRISIS, message
    assert SereneMindEngine().assess_distress(message).level != DistressLevel.SEVERE, message


@pytest.mark.asyncio
async def test_spiritual_framing_with_timeframe_live_route_is_crisis_preempted():
    ctx = _build_ctx("I'm going to leave my body tonight")
    result = await DistressStage().run(ctx)
    assert result is not None
    assert result.route_decision == "crisis_preempted"
    assert "Tele-MANAS" in result.final_answer
    assert "are you safe right now" in result.final_answer.lower()


@pytest.mark.asyncio
async def test_spiritual_framing_ambiguous_live_route_is_severe_checkin():
    ctx = _build_ctx("I want to leave this body")
    result = await DistressStage().run(ctx)
    assert result is not None
    assert result.route_decision == "crisis_preempted"
    assert "Tele-MANAS" in result.final_answer
    assert "are you safe right now" not in result.final_answer.lower()


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


# ---------------------------------------------------------------------------
# 4. Idiom exclusions (2026-09-28, owner-approved Task 2): a small, EXACT
# idiom list is masked out before pattern-matching, in BOTH
# serene_mind_engine.assess_distress() and guardrails.lightweight_handler's
# match_blocked_topic() (same compiled regex, IDIOM_EXCLUSIONS_RE — a
# single-source-of-truth fix, not two independently maintained copies, which
# is exactly the bug class the Kannada pre-screen/classifier divergence was).
# SUPERSEDES the earlier W2 decision to leave "kill myself laughing" as an
# accepted false positive — the owner's new decision is to exclude it.
# ---------------------------------------------------------------------------

IDIOM_PHRASES = [
    "kill myself laughing at this joke",
    "I'm dying of laughter over that meme",
    "I laughed myself to death at that video",
    "I died laughing at that",
    "that joke, I could die laughing",
]


@pytest.mark.parametrize("message", IDIOM_PHRASES)
def test_idiom_exclusions_are_not_crisis(message):
    assert SereneMindEngine().assess_distress(message).level != DistressLevel.CRISIS, message


@pytest.mark.asyncio
async def test_idiom_exclusion_live_route_is_not_crisis_preempted():
    """Also confirms the guardrail-level exclusion: without it,
    guardrail_self_harm_match would force CRISIS in DistressStage regardless
    of what the engine itself decided (the engine-only fix was not
    sufficient on its own — see guardrails/lightweight_handler.py's
    match_blocked_topic())."""
    from guardrails.lightweight_handler import LightweightGuardrailHandler

    text = "kill myself laughing at this joke"
    handler = LightweightGuardrailHandler()
    input_check = await handler._handle_input(text)
    assert input_check["blocked"] is False, input_check

    ctx = _build_ctx(text)
    distress_result = await DistressStage().run(ctx)
    assert distress_result is None, "idiom must not reach crisis pre-emption at all"
    assert not ctx.state.get("guardrail_self_harm_match")


# Every phrase from the W2 gap set and test_serene_mind.py's own ideation
# regression lists that must NEVER be excluded by IDIOM_EXCLUSIONS_RE — the
# parametrized guard the coordinator asked for. Sourced from (not duplicated
# logic, just the literal phrase strings, so a drift in either file's list
# is caught the next time this file is touched):
#   - this file's REPRESENTATIVE lists above
#   - tests/test_serene_mind.py::test_urgent_fix_2026_09_27_self_harm_phrasings_are_crisis
#   - tests/test_self_harm_crisis_unification.py::REPRESENTATIVE_SELF_HARM_PHRASES
REAL_IDEATION_PHRASES_MUST_NOT_BE_EXCLUDED = [
    "I am suicidal",
    "feeling suicidal",
    "suicide is something I think about",
    "I keep hurting myself",
    "I have been harming myself",
    "I started cutting myself",
    "how to die quickly",
    "way to die without pain",
    "my life is not worth living",
    "how many sleeping pills to die",
    "what does the teaching say about suicide",
    "I want to end my life",
    "I want to kill myself",
    "I want to self-harm",
    "I want to die",
    "I have no reason to live",
    "what is the way to die",
    "I wish I could sleep and never wake up",
    "I wish I were dead",
    "I don't want to exist",
    "I want to leave this body",
    "let me leave my body",
    "I'm going to leave my body tonight",
    "merge with the divine and end it",
    "she said she wants to kill herself",
]


@pytest.mark.parametrize("message", REAL_IDEATION_PHRASES_MUST_NOT_BE_EXCLUDED)
def test_idiom_exclusion_never_swallows_real_ideation(message):
    from services.serene_mind_engine import IDIOM_EXCLUSIONS_RE

    assert not IDIOM_EXCLUSIONS_RE.search(message), (
        f"{message!r} was masked by the idiom exclusion regex — it must not be"
    )
    # Belt-and-braces: the message must still classify as real distress
    # (anything above NONE) after going through the actual masking step.
    assert SereneMindEngine().assess_distress(message).level > DistressLevel.NONE, message


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
        SereneMindEngine().assess_distress("मैं अपनी जान देना चाहता हूं").level == DistressLevel.CRISIS
    )


if __name__ == "__main__":
    # ponytail: quick self-check without pytest
    test_wish_never_wake_up_is_severe_not_crisis()
    for m in SPIRITUAL_FRAMING_CRISIS_PHRASES:
        test_spiritual_framing_with_intent_plan_or_timeframe_is_crisis(m)
    for m in SPIRITUAL_FRAMING_SEVERE_PHRASES:
        test_spiritual_framing_ambiguous_is_severe_checkin(m)
    for m in SPIRITUAL_FRAMING_DOCTRINAL_PHRASES:
        test_spiritual_framing_doctrinal_questions_are_not_crisis(m)
    test_third_party_concern_is_crisis_with_distinct_response_type()
    for m in IDIOM_PHRASES:
        test_idiom_exclusions_are_not_crisis(m)
    for m in REAL_IDEATION_PHRASES_MUST_NOT_BE_EXCLUDED:
        test_idiom_exclusion_never_swallows_real_ideation(m)
    test_prescreen_and_classifier_cannot_diverge_kannada_saayabeku()
    test_prescreen_is_structurally_derived_from_classifier_not_a_second_list()
    test_hindi_jaan_dena_idiom_is_crisis()
    print("W2 crisis-test expansion self-checks passed")
