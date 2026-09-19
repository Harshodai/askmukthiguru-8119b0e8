"""Regression test for Workstream W5: Contradiction Gate in LettuceDetectService.

Verifies:
1. Negative control: an answer with 3 supported claims and 1 genuine doctrinal
   contradiction fails verification with score 0.0 and has_contradiction=True,
   regardless of the 75% supported claim ratio.
2. Contradiction classification: claims are split into entailment, neutral, and contradiction.
3. Numerical mutual exclusivity, polarity inversion, and doctrinal invariants are detected.
4. Pastoral blessings/optatives remain excluded and are not marked as contradictions (L-VERIFY-4).
5. Redaction refusal: _redact_unsupported_sentences refuses to salvage an answer containing a contradiction.
"""

from __future__ import annotations

from app.config import settings
from rag.nodes.generation import _redact_unsupported_sentences
from services.lettuce_detect_service import LettuceDetectService

DOCTRINE_CONTEXT = (
    "Sri Krishnaji teaches that there are only two states of being: the suffering state "
    "and the beautiful state. Suffering is not natural to human consciousness, and "
    "division in the mind creates inner conflict. In the beautiful state, one lives in "
    "connection, peace, and love."
)

ANSWER_WITH_CONTRADICTION = (
    "Sri Krishnaji teaches that there are only two states of being: the suffering state and the beautiful state. "
    "In the beautiful state, one lives in connection and peace. "
    "Division in the mind creates inner conflict. "
    "Sri Krishnaji also teaches that there are five states of being."
)


def test_contradiction_gate_hard_rejects_regardless_of_supported_ratio():
    """Negative control: 3 of 4 claims (75%) are supported, but 1 claim is a doctrinal contradiction.

    Before W5:
      - score was 0.75 >= faithfulness_floor (0.60)
      - has_contradiction was missing / False
      - _redact_unsupported_sentences salvaged the answer and allowed it to ship.

    After W5:
      - has_contradiction is True
      - is_faithful is False
      - score is 0.0 (hard reject)
      - the 4th claim is classified as 'contradiction'
      - _redact_unsupported_sentences returns None (refuses to ship).
    """
    svc = LettuceDetectService(embedder=None)
    result = svc.score_faithfulness(
        "What are the states of being?", DOCTRINE_CONTEXT, ANSWER_WITH_CONTRADICTION
    )

    # Contradiction flag and hard rejection must be present
    assert result.get("has_contradiction") is True, f"Expected has_contradiction=True, got {result}"
    assert result["is_faithful"] is False
    assert result["score"] == 0.0, f"Expected score=0.0 on contradiction, got {result['score']}"

    # Verify claim-level classifications
    claims = result.get("claims", [])
    assert len(claims) == 4
    contradiction_claims = [c for c in claims if c.get("classification") == "contradiction"]
    assert len(contradiction_claims) == 1
    assert "five states" in contradiction_claims[0]["text"]
    assert contradiction_claims[0].get("contradiction") is True

    # Verify redaction refuses to ship
    redacted = _redact_unsupported_sentences(result, floor=settings.faithfulness_floor)
    assert redacted is None, f"Expected redaction to return None on contradiction, got {redacted}"


def test_neutral_unsupported_claim_is_not_contradiction():
    """An ungrounded factual addition is classified as 'neutral', not 'contradiction'."""
    svc = LettuceDetectService(embedder=None)
    answer_with_neutral = (
        "Sri Krishnaji teaches that there are only two states of being: the suffering state and the beautiful state. "
        "Sri Krishnaji was born in the twentieth century."
    )
    result = svc.score_faithfulness(
        "What are the states of being?", DOCTRINE_CONTEXT, answer_with_neutral
    )

    assert result.get("has_contradiction") is False
    claims = result.get("claims", [])
    neutral_claims = [c for c in claims if c.get("classification") == "neutral"]
    assert len(neutral_claims) == 1
    assert "twentieth century" in neutral_claims[0]["text"]


def test_polarity_inversion_contradiction():
    """Affirming what context explicitly negates must be detected as a contradiction."""
    svc = LettuceDetectService(embedder=None)
    # Context explicitly states: "Suffering is not natural to human consciousness"
    answer = (
        "In the beautiful state, one lives in connection, peace, and love. "
        "Suffering is natural to human consciousness."
    )
    result = svc.score_faithfulness("Is suffering natural?", DOCTRINE_CONTEXT, answer)

    assert result.get("has_contradiction") is True
    assert result["score"] == 0.0
    contradiction_claims = [
        c for c in result.get("claims", []) if c.get("classification") == "contradiction"
    ]
    assert len(contradiction_claims) == 1
    assert "natural" in contradiction_claims[0]["text"]


def test_optatives_and_blessings_never_flagged_as_contradiction():
    """Blessings have no truth value and must stay excluded from contradiction scoring (L-VERIFY-4)."""
    svc = LettuceDetectService(embedder=None)
    answer = (
        "In the beautiful state, one lives in connection, peace, and love. "
        "May this knowledge bring peace to your heart as you continue your journey."
    )
    result = svc.score_faithfulness("What is the beautiful state?", DOCTRINE_CONTEXT, answer)

    assert result.get("has_contradiction") is False
    # The blessing must not be scored as a contradiction
    claims = result.get("claims", [])
    assert not any(c.get("classification") == "contradiction" for c in claims)
