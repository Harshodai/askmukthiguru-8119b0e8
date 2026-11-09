"""One content vocabulary, one verdict.

Before ``services.first_person_content_assessment`` the same phrases were matched
by four modules with four severities, so a fix in one moved the failure to
another. These tests pin the union contract: whatever any former copy excluded
is still excluded, the wellbeing framing is a notice (never an exclusion), and
query-scoped detectors are skipped — not guessed — when no query is available.
"""

from __future__ import annotations

import pytest

from domain.first_person_decision import AssessmentKind, FindingSeverity
from services.first_person_content_assessment import (
    CLINICAL_CLAIM_CODE,
    EVENT_BOUND_CODE,
    MEDICAL_CLAIM_NOTICE,
    OUTCOME_PROMISE_CODE,
    WELLBEING_FRAMING_CODE,
    assess_content,
    blocks_serving,
    notice_copy,
)

BENIGN_QUERY = "What is inner peace?"


@pytest.mark.parametrize(
    "text",
    [
        "This practice will cure your cancer.",
        "There is a state of stress increases the insulin level and causes physical breakdown.",
        "When you stay in stress for years, you are getting diseased and losing vitality.",
        "Scientists have scientifically proven that meditation repairs neurons in your brain.",
        "You will be healed physically and emotionally by this.",
        "Chemical changes come as health issues.",
        "The wrong signal to the universe returns as illness.",
        "Love itself has tremendous power to heal.",
    ],
)
def test_clinical_claims_are_excluded(text):
    assessment = assess_content(text, query=BENIGN_QUERY)
    assert assessment.may_serve is False
    assert CLINICAL_CLAIM_CODE in assessment.exclusion_codes


def test_causal_etiology_is_its_own_kind_and_also_excluded():
    assessment = assess_content(
        "These diseases are actually caused by undigested material in the body.",
        query=BENIGN_QUERY,
    )
    assert assessment.may_serve is False
    kinds = {finding.kind for finding in assessment.findings}
    assert AssessmentKind.CAUSAL_ETIOLOGY in kinds
    # The reason code is shared with clinical claims so downstream gates and
    # audit records keep one stable token.
    assert CLINICAL_CLAIM_CODE in assessment.exclusion_codes


@pytest.mark.parametrize(
    "text",
    [
        "Your problems will all melt like ice in the heat of the sun.",
        "This is a guaranteed outcome for everyone who attends.",
        "I promise you a miracle if you follow this.",
        "You will never again feel this sadness.",
    ],
)
def test_outcome_promises_are_excluded(text):
    assessment = assess_content(text, query=BENIGN_QUERY)
    assert assessment.may_serve is False
    assert OUTCOME_PROMISE_CODE in assessment.exclusion_codes


def test_wellbeing_framing_is_a_notice_not_an_exclusion():
    text = "When you truly feel peace every muscle in your body relaxes."
    assessment = assess_content(text, query=BENIGN_QUERY)
    assert assessment.may_serve is True
    assert WELLBEING_FRAMING_CODE in assessment.reason_codes
    assert assessment.severity is FindingSeverity.NOTICE
    assert notice_copy(assessment) == (MEDICAL_CLAIM_NOTICE,)


def test_wellbeing_framing_never_masks_an_exclusion():
    """Union rule: a text that is both framed and clinical is excluded."""
    text = "When inner disturbance leaves your body agitated, this will cure your cancer."
    assessment = assess_content(text, query=BENIGN_QUERY)
    assert assessment.may_serve is False
    assert WELLBEING_FRAMING_CODE in assessment.reason_codes
    assert CLINICAL_CLAIM_CODE in assessment.exclusion_codes
    # No notice is offered for a clip that will not be served at all.
    assert notice_copy(assessment) == ()


def test_unsolicited_self_harm_reference_is_excluded_for_a_benign_query():
    assessment = assess_content("Some people who are suicidal simply withdraw.", query="What is love?")
    assert assessment.may_serve is False
    assert AssessmentKind.SELF_HARM in {f.kind for f in assessment.findings}


@pytest.mark.parametrize(
    "query",
    ["How do I support someone who is suicidal?", "What does mental health mean?", "Tell me about depression"],
)
def test_self_harm_content_is_educational_when_the_question_asks(query):
    assessment = assess_content("Some people who are suicidal simply withdraw.", query=query)
    assert assessment.may_serve is True


def test_no_query_skips_query_scoped_detectors_rather_than_guessing():
    # Cache replay / preview validation: the query is unknown, so the
    # query-scoped detectors must be skipped, not assumed benign or harmful.
    assert assess_content("Some people who are suicidal simply withdraw.").may_serve is True
    # Unconditional exclusions still fail closed with no query.
    assert assess_content("This will cure your cancer.").may_serve is False


def test_relationship_violence_wording_needs_a_relationship_query():
    text = "He hit her again and again until she could not stand."
    assert assess_content(text, query="How do I bake a cake?").may_serve is True
    # The relationship-safety notion of a query is owned by the existing
    # guardrail (repair/heal/conflict framing); this detector inherits it rather
    # than inventing a second vocabulary.
    assert assess_content(text, query="My partner and I keep fighting, what do I do?").may_serve is False


def test_event_and_cross_turn_signals_are_review_not_exclusion():
    assessment = assess_content("During the covid lockdown we sat together.", query=BENIGN_QUERY)
    assert assessment.may_serve is True
    assert assessment.requires_review is True
    assert EVENT_BOUND_CODE in assessment.review_codes


@pytest.mark.parametrize(
    "text",
    [
        "Let us move into meditation now.",
        "Individual transformation leads to world transformation. Let's move into meditation.",
        "When the mind is quiet, move into meditation now.",
    ],
)
def test_live_meditation_transitions_are_flagged_as_event_bound(text):
    assessment = assess_content(text, query=BENIGN_QUERY)
    assert assessment.may_serve is True
    assert assessment.requires_review is True
    assert EVENT_BOUND_CODE in assessment.review_codes


def test_empty_text_is_clean():
    assert assess_content("").may_serve is True
    assert assess_content("   ").findings == ()


def test_blocks_serving_is_the_predicate_form():
    assert blocks_serving("This will cure your cancer.") is True
    assert blocks_serving("Stillness is the nature of awareness.") is False


def test_assessment_is_deterministic():
    text = "When you truly feel peace every muscle in your body relaxes."
    assert assess_content(text, query=BENIGN_QUERY) == assess_content(text, query=BENIGN_QUERY)


def test_semantic_clean_allows_spiritual_metaphor_as_wellbeing_notice():
    # Without semantic judge, broad regex excludes "power to heal" as a clinical claim
    text = "Love itself has tremendous power to heal the wounded heart and restore peace."
    assessment_offline = assess_content(text, query=BENIGN_QUERY)
    assert assessment_offline.may_serve is False
    assert CLINICAL_CLAIM_CODE in assessment_offline.exclusion_codes

    # With semantic judge content_safety="clean", spiritual metaphor is categorized as wellbeing notice
    assessment_semantic = assess_content(text, query=BENIGN_QUERY, content_safety="clean")
    assert assessment_semantic.may_serve is True
    assert CLINICAL_CLAIM_CODE not in assessment_semantic.exclusion_codes
    assert WELLBEING_FRAMING_CODE in assessment_semantic.reason_codes


def test_semantic_clean_still_excludes_literal_clinical_disease_claims():
    text = "This meditation will cure your cancer and heal your diabetes."
    # Even if judge falsely tagged "clean", literal clinical claims must fail-safe and exclude
    assessment = assess_content(text, query=BENIGN_QUERY, content_safety="clean")
    assert assessment.may_serve is False
    assert CLINICAL_CLAIM_CODE in assessment.exclusion_codes


def test_content_safety_clinical_promise_and_distress_excludes():
    text = "Sit in stillness and discover your inner peace."
    assessment_promise = assess_content(text, query=BENIGN_QUERY, content_safety="clinical_promise")
    assert assessment_promise.may_serve is False
    assert OUTCOME_PROMISE_CODE in assessment_promise.exclusion_codes

    assessment_distress = assess_content(text, query=BENIGN_QUERY, content_safety="distress")
    assert assessment_distress.may_serve is False


def test_deterministic_self_harm_preempts_regardless_of_semantic_clean():
    text = "The participant spoke about suicidal thoughts in their life."
    # Even with content_safety="clean", deterministic crisis/self-harm regexes immediately exclude
    assessment = assess_content(text, query=BENIGN_QUERY, content_safety="clean")
    assert assessment.may_serve is False
    assert "unsolicited_self_harm_reference" in assessment.exclusion_codes

