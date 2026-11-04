"""Regression tests for deterministic first-person evidence-policy decisions."""

from domain.first_person_evidence import EvidenceAction
from domain.first_person_safety import SAFETY_POLICY_VERSION
from services.first_person_evidence_policy import (
    POLICY_VERSION,
    first_person_evidence_policy,
)


def test_violence_policy_is_query_scoped_and_returns_reason_code():
    clip = "As a husband, he doesn't mind being stabbed by his angry wife to calm her down."
    relationship_question = "How do I deal with anger at my husband?"

    blocked = first_person_evidence_policy.assess_contextual_safety(relationship_question, clip)
    unrelated = first_person_evidence_policy.assess_contextual_safety(
        "What is the Beautiful State?", clip
    )

    assert blocked.action is EvidenceAction.EXCLUDE
    assert blocked.reason_codes == ("violent_relationship_context",)
    assert unrelated.action is EvidenceAction.ALLOW
    assert unrelated.reason_codes == ()
    assert blocked.policy_version == POLICY_VERSION


def test_unsolicited_self_harm_reference_is_excluded():
    decision = first_person_evidence_policy.assess_contextual_safety(
        "How can I find inner peace?",
        "A teacher mentions suicidal thoughts in this otherwise unrelated passage.",
    )

    assert decision.action is EvidenceAction.EXCLUDE
    assert decision.reason_codes == ("unsolicited_self_harm_reference",)


def test_explicit_self_harm_query_is_not_blocked_by_the_clip_context_filter_alone():
    decision = first_person_evidence_policy.assess_contextual_safety(
        "How can I support a person with suicidal thoughts?",
        "A teacher mentions suicidal thoughts in this passage.",
    )

    # This lexical context filter does not replace the upstream crisis/safety route.
    assert decision.action is EvidenceAction.ALLOW_WITH_CONTEXT


def test_phase3_event_bound_clip_alone_is_sent_to_review_by_shared_facade():
    decision = first_person_evidence_policy.assess_contextual_safety(
        "What is love?",
        "During the covid pandemic, many people had to rethink how they cope.",
    )

    assert decision.action is EvidenceAction.NEEDS_REVIEW
    assert decision.reason_codes == ("event_bound",)


def test_phase3_event_bound_plus_another_exclusion_stays_excluded():
    decision = first_person_evidence_policy.assess_contextual_safety(
        "What is inner peace?",
        "During the covid pandemic, meditation has been scientifically proven to cure depression.",
    )

    assert decision.action is EvidenceAction.EXCLUDE
    assert {"event_bound", "health_claim"}.issubset(decision.reason_codes)


def test_phase3_health_and_outcome_claims_are_excluded_by_shared_facade():
    health = first_person_evidence_policy.assess_contextual_safety(
        "What is inner peace?",
        "Meditation has been scientifically proven to cure depression.",
    )
    outcome = first_person_evidence_policy.assess_contextual_safety(
        "What practice should I do?",
        "If you follow this practice, you will definitely achieve lasting happiness.",
    )

    assert health.action is EvidenceAction.EXCLUDE
    assert "health_claim" in health.reason_codes
    assert outcome.action is EvidenceAction.EXCLUDE
    assert "outcome_promise" in outcome.reason_codes


def test_phase3_complete_audience_question_is_not_dangling_in_shared_facade():
    decision = first_person_evidence_policy.assess_contextual_safety(
        "What is suffering?",
        "Suffering asks us to observe the mind carefully. What do you do?",
    )

    assert decision.action is EvidenceAction.ALLOW
    assert "dangling_dependency" not in decision.reason_codes


def test_composed_policy_version_contains_phase3_version():
    assert SAFETY_POLICY_VERSION in POLICY_VERSION


def test_shared_facade_allows_complete_audience_question():
    decision = first_person_evidence_policy.assess_contextual_safety(
        "What is love?",
        "How can we address this?",
    )

    assert decision.action is EvidenceAction.ALLOW
    assert "dangling_dependency" not in decision.reason_codes


def test_shared_facade_allows_complete_should_we_question():
    decision = first_person_evidence_policy.assess_contextual_safety(
        "What is love?",
        "Why should we continue?",
    )

    assert decision.action is EvidenceAction.ALLOW
    assert "dangling_dependency" not in decision.reason_codes


def test_shared_facade_keeps_true_elliptical_tail_under_review():
    decision = first_person_evidence_policy.assess_contextual_safety(
        "What is love?",
        "We have explored this together. How do we?",
    )

    assert decision.action is EvidenceAction.NEEDS_REVIEW
    assert "dangling_dependency" in decision.reason_codes


def test_context_standalone_policy_rejects_a_dangling_question_tail():
    text = (
        "Suffering is a call to awaken. It is a moment of quiet attention that lets us "
        "observe the mind without choosing and notice its movement carefully. What about you?"
    )

    decision = first_person_evidence_policy.assess_context_standalone((text,))

    assert decision.action is EvidenceAction.EXCLUDE
    assert decision.reason_codes == ("dangling_question_tail",)
