"""A redacted answer is grounded, not an abstention.

`grounding_state_for` derives the user-visible state independently of the graph.
It special-cased the excerpt fallback but not redaction, so an answer whose every
shipped sentence had been verifier-grounded was reported as "abstained" — which
then feeds the hallucination analytics.
"""

from types import SimpleNamespace

from app.grounding import grounding_state_for


def _result(method, citations=(("u", "t"),), hallucination=False, **kw):
    return SimpleNamespace(
        blocked=False,
        intent="FACTUAL",
        verification={"method": method, "passed": True, "redacted_sentences": 2},
        citations=list(citations),
        hallucination_flag=hallucination,
        citations_verified=True,
        answer_evidence=None,
        **kw,
    )


def test_redacted_answer_is_grounded():
    assert grounding_state_for(_result("redacted_unsupported_claims")) == "grounded"


def test_redaction_without_citations_is_not_promoted():
    assert grounding_state_for(_result("redacted_unsupported_claims", citations=())) != "grounded"


def test_hallucination_flag_still_blocks_the_grounded_label():
    assert (
        grounding_state_for(_result("redacted_unsupported_claims", hallucination=True))
        != "grounded"
    )


def test_safety_intent_still_wins():
    r = _result("redacted_unsupported_claims")
    r.intent = "DISTRESS"
    assert grounding_state_for(r) == "safety_redirect"
