"""Uncertain completeness may relax a clip to "related"; it may not skip later gates.

fb404456 returned `_related(...)` straight from the completeness gate, so an UNCERTAIN
span skipped the contextual-safety gate, the answerability NO veto, coreference, the
question-only check and reconstruction. `boundary_uncertain` (the pattern it cites) runs
after all of those. These pin the gate order for both the span and the parent status.
"""

from __future__ import annotations

import pytest

from domain.first_person_context import CompletenessStatus
from services.first_person_context_harness import (
    FirstPersonContextHarness,
    HarnessDecision,
    HarnessPolicy,
)
from tests.test_first_person_context_harness import context, span  # noqa: F401
from tests.test_first_person_context_harness import _synthetic_registry  # noqa: F401 - autouse

_POLICY = HarnessPolicy(allow_fragment_with_antecedent=True, allow_uncertain_completeness=True)


def _uncertain_cases():
    return [
        ("span", lambda **kw: context([span(completeness_status=CompletenessStatus.UNCERTAIN, **kw)])),
        ("parent", lambda **kw: context([span(**kw)], completeness_status=CompletenessStatus.UNCERTAIN)),
    ]


@pytest.mark.parametrize("label,make", _uncertain_cases())
def test_contextual_safety_still_runs(label, make, monkeypatch):
    class Unsafe:
        may_serve, reason_codes = False, ("violent_relationship_context",)

    monkeypatch.setattr(
        "services.first_person_context_harness.first_person_evidence_policy.assess_contextual_safety",
        lambda *a, **k: Unsafe(),
    )
    decision = FirstPersonContextHarness(_POLICY).decide(make(), answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN, label
    assert decision.abstain_reason == "violent_relationship_context"


@pytest.mark.parametrize("label,make", _uncertain_cases())
def test_answerability_no_still_vetoes(label, make):
    decision = FirstPersonContextHarness(_POLICY).decide(make(), answerability="no")
    assert decision.decision is HarnessDecision.ABSTAIN, label
    assert decision.abstain_reason == "answerability_no"


@pytest.mark.parametrize("label,make", _uncertain_cases())
def test_question_only_clip_still_abstains(label, make):
    decision = FirstPersonContextHarness(_POLICY).decide(
        make(text="What is suffering? Why do we suffer? Is suffering necessary?"),
        answerability="yes",
    )
    assert decision.decision is HarnessDecision.ABSTAIN, label
    assert decision.abstain_reason == "question_only_clip"


@pytest.mark.parametrize("label,make", _uncertain_cases())
def test_clean_uncertain_clip_is_still_served_as_related(label, make):
    decision = FirstPersonContextHarness(_POLICY).decide(make(), answerability="yes")
    assert decision.decision is HarnessDecision.SERVE_RELATED_NOT_DIRECT, label
    assert decision.abstain_reason == "completeness_uncertain"
    assert decision.gates["completeness"] is False
    assert decision.gates["contextual_safety"] is True  # the gate ran
