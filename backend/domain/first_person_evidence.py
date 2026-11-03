"""Small immutable decisions for first-person evidence policy.

This model deliberately does not represent a rendered answer, retrieval result,
rights register, or calibrated confidence score. Those remain owned by their
existing domain and serving contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EvidenceAction(StrEnum):
    ALLOW = "allow"
    ALLOW_WITH_CONTEXT = "allow_with_context"
    EXCLUDE = "exclude"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True, slots=True)
class EvidenceDecision:
    """Policy outcome with bounded reason codes and no user/source prose."""

    action: EvidenceAction
    reason_codes: tuple[str, ...] = ()
    policy_version: str = "first_person_evidence_v1"

    @property
    def may_serve(self) -> bool:
        """Only explicit allow outcomes may proceed to the existing serve gates."""
        return self.action in (EvidenceAction.ALLOW, EvidenceAction.ALLOW_WITH_CONTEXT)


if __name__ == "__main__":
    allowed = EvidenceDecision(EvidenceAction.ALLOW)
    excluded = EvidenceDecision(EvidenceAction.EXCLUDE, ("unsolicited_self_harm_reference",))
    assert allowed.may_serve
    assert not excluded.may_serve
    print("first_person_evidence self-check passed")
