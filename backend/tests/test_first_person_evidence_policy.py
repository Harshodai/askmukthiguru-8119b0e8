"""Regression tests for deterministic first-person evidence-policy decisions."""

from domain.first_person_evidence import EvidenceAction
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
    assert decision.action is EvidenceAction.ALLOW


def test_context_standalone_policy_rejects_a_dangling_question_tail():
    text = (
        "Suffering is a call to awaken. It is a moment of quiet attention that lets us "
        "observe the mind without choosing and notice its movement carefully. What do you do?"
    )

    decision = first_person_evidence_policy.assess_context_standalone((text,))

    assert decision.action is EvidenceAction.EXCLUDE
    assert decision.reason_codes == ("dangling_question_tail",)
