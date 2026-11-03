"""Typed safety dimension model for first-person contextual safety decisions.

This model deliberately does not represent a rendered answer, retrieval result,
rights register, or calibrated confidence score. Those remain owned by their
existing domain and serving contracts.

Safety dimensions are layered on top of the existing evidence policy and do not
replace it. All decisions are deterministic; no LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

SAFETY_POLICY_VERSION = "first_person_safety_v1"


class SafetySignalType(StrEnum):
    MENTION = "mention"  # topic is mentioned but not the focus
    EDUCATION = "education"  # explicitly educational/explanatory context
    DISTRESS = "distress"  # personal distress expressed
    INSTRUCTION = "instruction"  # request for instructions on harmful act
    EVENT_DEP = "event_dep"  # event/discourse dependency (pandemic, session-context)
    CROSS_TURN = "cross_turn"  # cross-speaker turn reference / host bleed


class SafetyCategory(StrEnum):
    SELF_HARM = "self_harm"
    VIOLENCE = "violence"
    MEDICAL_CLAIM = "medical_claim"
    SEXUAL_CONTENT = "sexual_content"
    EVENT_BOUND = "event_bound"
    CROSS_TURN_REFERENCE = "cross_turn_reference"
    UNSOLICITED_SENSITIVE = "unsolicited_sensitive"
    OUTCOME_PROMISE = "outcome_promise"
    DANGLING_DEPENDENCY = "dangling_dependency"


@dataclass(frozen=True, slots=True)
class SafetyDimension:
    """A single scored safety signal attached to a candidate or query.

    ``detector`` carries the detector name for auditability; it must never
    contain user prose or candidate text.
    """

    category: SafetyCategory
    signal_type: SafetySignalType
    confidence: float  # 0.0–1.0
    detector: str  # detector name for auditability (no user prose)
    policy_version: str = SAFETY_POLICY_VERSION


@dataclass(frozen=True, slots=True)
class ContextualSafetyDecision:
    """Policy outcome combining all triggered safety dimensions.

    ``reason_codes`` is a bounded vocabulary of short snake_case strings;
    it must never contain user prose or candidate text.
    """

    action: Literal["allow", "allow_with_context", "exclude", "needs_review"]
    dimensions: tuple[SafetyDimension, ...]
    reason_codes: tuple[str, ...]
    policy_version: str = SAFETY_POLICY_VERSION

    @property
    def may_serve(self) -> bool:
        """Only allow/allow_with_context outcomes may proceed to the serve gates."""
        return self.action in ("allow", "allow_with_context")

    @property
    def is_event_bound(self) -> bool:
        """True when at least one dimension signals an event/discourse dependency."""
        return any(d.category == SafetyCategory.EVENT_BOUND for d in self.dimensions)


if __name__ == "__main__":
    _allowed = ContextualSafetyDecision(
        action="allow",
        dimensions=(),
        reason_codes=(),
    )
    _excluded = ContextualSafetyDecision(
        action="exclude",
        dimensions=(
            SafetyDimension(
                category=SafetyCategory.UNSOLICITED_SENSITIVE,
                signal_type=SafetySignalType.MENTION,
                confidence=1.0,
                detector="self_harm_unsolicited_detector",
            ),
        ),
        reason_codes=("unsolicited_self_harm_reference",),
    )
    _event = ContextualSafetyDecision(
        action="exclude",
        dimensions=(
            SafetyDimension(
                category=SafetyCategory.EVENT_BOUND,
                signal_type=SafetySignalType.EVENT_DEP,
                confidence=1.0,
                detector="event_marker_detector",
            ),
        ),
        reason_codes=("event_bound",),
    )
    assert _allowed.may_serve
    assert not _excluded.may_serve
    assert not _excluded.is_event_bound
    assert _event.is_event_bound
    print("first_person_safety self-check passed")
