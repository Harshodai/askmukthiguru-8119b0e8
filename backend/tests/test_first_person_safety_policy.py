"""Targeted regressions for FirstPersonSafetyPolicy (Phase 3).

Test IDs mirror the editorial candidate codes used in the task plan
(q019, q040, q061, q056, q003, …) so failures are traceable back to
the specific editorial case that motivated each rule.

No network, no Qdrant, no LLM calls.
"""

from __future__ import annotations

import pytest

from domain.first_person_safety import (
    ContextualSafetyDecision,
    SafetyCategory,
    SafetySignalType,
)
from services.first_person_safety_policy import FirstPersonSafetyPolicy


@pytest.fixture()
def policy() -> FirstPersonSafetyPolicy:
    return FirstPersonSafetyPolicy()


# ---------------------------------------------------------------------------
# q019: benign love query + self-harm clip → exclude, unsolicited_sensitive
# ---------------------------------------------------------------------------


def test_q019_benign_love_query_self_harm_clip_excluded(policy):
    """A seeker asking about love must never receive a self-harm clip."""
    result = policy.evaluate(
        query="How can I experience more love and connection?",
        candidate_text=("People who engage in self-harm often feel disconnected from others."),
    )
    assert result.action == "exclude"
    assert "unsolicited_self_harm_reference" in result.reason_codes
    assert not result.may_serve


def test_q019_benign_peace_query_suicide_clip_excluded(policy):
    """Suicidal term in candidate + peace query → unsolicited → exclude."""
    result = policy.evaluate(
        query="How do I find inner peace?",
        candidate_text=("Suicidal thoughts can arise when someone has lost all hope."),
    )
    assert result.action == "exclude"
    assert "unsolicited_self_harm_reference" in result.reason_codes


# ---------------------------------------------------------------------------
# q040: pandemic/lockdown clip + general query → exclude, event_bound
# ---------------------------------------------------------------------------


def test_q040_pandemic_clip_general_query_excluded(policy):
    """A clip referencing covid/lockdown is event-bound; exclude for a general query."""
    result = policy.evaluate(
        query="How do I deal with stress?",
        candidate_text=("During the covid pandemic, many of us had to rethink how we cope."),
    )
    assert result.action == "exclude"
    assert "event_bound" in result.reason_codes
    assert result.is_event_bound


def test_q040_lockdown_clip_excluded(policy):
    """Explicit lockdown mention → event_bound → exclude."""
    result = policy.evaluate(
        query="What is the path to happiness?",
        candidate_text=("In the lockdown period, gratitude practices became very popular."),
    )
    assert result.action == "exclude"
    assert result.is_event_bound


def test_q040_session_reference_clip_excluded(policy):
    """Clip referencing 'the previous session' is session-event-bound → exclude."""
    result = policy.evaluate(
        query="Tell me about awareness.",
        candidate_text=("Like I said in the last session, awareness starts with the breath."),
    )
    assert result.action == "exclude"
    assert result.is_event_bound


# ---------------------------------------------------------------------------
# q061: dangling rhetorical tail → needs_review, dangling_dependency
# ---------------------------------------------------------------------------


def test_q061_dangling_question_tail_needs_review(policy):
    """A clip ending in a rhetorical question aimed at the audience → needs_review."""
    result = policy.evaluate(
        query="What is the nature of suffering?",
        candidate_text=(
            "We all experience suffering in different ways. What do you do when it arises?"
        ),
    )
    assert result.action == "needs_review"
    assert "dangling_dependency" in result.reason_codes


def test_q061_how_can_we_tail_needs_review(policy):
    """'How can we …?' at end of clip → dangling_dependency → needs_review."""
    result = policy.evaluate(
        query="How do I overcome anger?",
        candidate_text=(
            "Anger arises from a deep sense of unmet expectation. How can we address this?"
        ),
    )
    assert result.action == "needs_review"
    assert "dangling_dependency" in result.reason_codes


# ---------------------------------------------------------------------------
# q056: orphan opener → needs_review (dangling_dependency via orphan_opener)
# ---------------------------------------------------------------------------


def test_q056_orphan_opener_they_needs_review(policy):
    """Clip beginning with an orphan pronoun 'they' is context-incomplete → needs_review."""
    result = policy.evaluate(
        query="How do I relate to difficult people?",
        candidate_text=("They are acting from a place of fear, not from a place of strength."),
    )
    assert result.action == "needs_review"
    assert "dangling_dependency" in result.reason_codes


def test_q056_orphan_opener_because_needs_review(policy):
    """'Because …' opener implies missing premise → needs_review."""
    result = policy.evaluate(
        query="Why do we suffer?",
        candidate_text=("Because the mind clings to what it cannot control, suffering arises."),
    )
    assert result.action == "needs_review"
    assert "dangling_dependency" in result.reason_codes


# ---------------------------------------------------------------------------
# q003: clean clip + benign query → allow
# ---------------------------------------------------------------------------


def test_q003_clean_clip_benign_query_allowed(policy):
    """A direct teaching clip matched to a relevant benign query → allow."""
    result = policy.evaluate(
        query="What is inner peace?",
        candidate_text=(
            "Inner peace arises naturally when the mind stops its restless movement "
            "and settles into awareness of the present moment."
        ),
    )
    assert result.action == "allow"
    assert result.may_serve
    assert result.reason_codes == ()
    assert result.dimensions == ()


# ---------------------------------------------------------------------------
# Explicit mental-health query + educational self-harm content → allow_with_context
# ---------------------------------------------------------------------------


def test_mental_health_query_educational_self_harm_allow_with_context(policy):
    """Query explicitly asks about self-harm support → educational context → allow_with_context."""
    result = policy.evaluate(
        query="How can I help someone who is engaging in self-harm?",
        candidate_text=(
            "Self-harm is a coping mechanism used when inner pain feels unbearable; "
            "compassionate presence and professional support are both essential."
        ),
    )
    assert result.action == "allow_with_context"
    assert result.may_serve
    assert "self_harm_educational_context" in result.reason_codes


def test_suicidal_topic_query_clip_educational(policy):
    """Query explicitly mentions 'suicidal' → self-harm clip is educational, not unsolicited."""
    result = policy.evaluate(
        query="What should I say when a friend tells me they feel suicidal?",
        candidate_text=(
            "Suicidal thoughts are a signal that someone needs immediate compassion "
            "and professional help; never dismiss or minimise what they share."
        ),
    )
    assert result.action == "allow_with_context"
    assert result.may_serve


# ---------------------------------------------------------------------------
# Health claim clip → exclude
# ---------------------------------------------------------------------------


def test_health_claim_clip_excluded(policy):
    """A clip containing a health/cure claim must be excluded."""
    result = policy.evaluate(
        query="Can meditation help my health?",
        candidate_text=(
            "Meditation has been scientifically proven to cure depression and anxiety."
        ),
    )
    assert result.action == "exclude"
    assert "health_claim" in result.reason_codes
    assert not result.may_serve


def test_cancer_claim_excluded(policy):
    """Cancer mention in a curative context → health_claim → exclude."""
    result = policy.evaluate(
        query="Can spirituality heal the body?",
        candidate_text=("I have seen people healed of cancer through deep prayer and presence."),
    )
    assert result.action == "exclude"
    assert "health_claim" in result.reason_codes


# ---------------------------------------------------------------------------
# Outcome promise clip → exclude
# ---------------------------------------------------------------------------


def test_outcome_promise_excluded(policy):
    """A clip making a guaranteed-outcome promise → exclude."""
    result = policy.evaluate(
        query="How do I become happy?",
        candidate_text=(
            "If you follow this practice, you will definitely achieve lasting happiness."
        ),
    )
    assert result.action == "exclude"
    assert "outcome_promise" in result.reason_codes


def test_hundred_percent_guaranteed_excluded(policy):
    """'100% guaranteed' in a clip → outcome_promise → exclude."""
    result = policy.evaluate(
        query="What practice should I do?",
        candidate_text=("This technique is 100% guaranteed to remove all stress from your life."),
    )
    assert result.action == "exclude"
    assert "outcome_promise" in result.reason_codes


# ---------------------------------------------------------------------------
# Empty query + empty candidate → allow (no signals, fail-open for empty)
# ---------------------------------------------------------------------------


def test_empty_query_and_candidate_allow(policy):
    """Empty inputs produce no safety signals → allow (fail-open for empty)."""
    result = policy.evaluate(query="", candidate_text="")
    assert result.action == "allow"
    assert result.reason_codes == ()
    assert result.dimensions == ()


def test_whitespace_only_inputs_allow(policy):
    """Whitespace-only inputs also produce no safety signals → allow."""
    result = policy.evaluate(query="   ", candidate_text="\n\t ")
    assert result.action == "allow"


# ---------------------------------------------------------------------------
# Exception in detector → exclude (fail-closed)
# ---------------------------------------------------------------------------


def test_exception_in_detector_returns_exclude(policy, monkeypatch):
    """If any internal detector raises, the policy must fail-closed → exclude."""

    def _boom(text):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(
        "services.first_person_safety_policy._SELF_HARM_CLIP_RE",
        type("_FakeRE", (), {"search": staticmethod(_boom)})(),
    )
    result = policy.evaluate(
        query="How do I find peace?",
        candidate_text="A calm mind sees things clearly.",
    )
    assert result.action == "exclude"
    assert "detector_exception" in result.reason_codes


# ---------------------------------------------------------------------------
# Structural / property tests on ContextualSafetyDecision
# ---------------------------------------------------------------------------


def test_may_serve_true_for_allow(policy):
    result = policy.evaluate(
        query="What is awareness?",
        candidate_text=("Awareness is the silent background in which all experiences arise."),
    )
    assert result.may_serve


def test_may_serve_false_for_exclude():
    decision = ContextualSafetyDecision(
        action="exclude",
        dimensions=(),
        reason_codes=("event_bound",),
    )
    assert not decision.may_serve


def test_may_serve_true_for_allow_with_context():
    decision = ContextualSafetyDecision(
        action="allow_with_context",
        dimensions=(),
        reason_codes=("self_harm_educational_context",),
    )
    assert decision.may_serve


def test_is_event_bound_true_when_event_dimension_present():
    from domain.first_person_safety import SafetyDimension

    dim = SafetyDimension(
        category=SafetyCategory.EVENT_BOUND,
        signal_type=SafetySignalType.EVENT_DEP,
        confidence=1.0,
        detector="event_marker_detector",
    )
    decision = ContextualSafetyDecision(
        action="exclude",
        dimensions=(dim,),
        reason_codes=("event_bound",),
    )
    assert decision.is_event_bound


def test_is_event_bound_false_when_no_event_dimension(policy):
    result = policy.evaluate(
        query="What is compassion?",
        candidate_text=("Compassion arises when we recognise the shared humanity in all beings."),
    )
    assert not result.is_event_bound


# ---------------------------------------------------------------------------
# Policy version propagation
# ---------------------------------------------------------------------------


def test_policy_version_propagated(policy):
    result = policy.evaluate(
        query="What is stillness?",
        candidate_text="Stillness is not the absence of movement but its ground.",
    )
    assert result.policy_version == "first_person_safety_v1"


def test_singleton_has_correct_policy_version():
    from services.first_person_safety_policy import first_person_safety_policy

    assert first_person_safety_policy.POLICY_VERSION == "first_person_safety_v1"
