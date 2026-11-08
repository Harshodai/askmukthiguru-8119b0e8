"""Contextual safety policy for first-person serving paths.

Extends the existing deterministic evidence gates with typed SafetyDimensions
that distinguish query-context from candidate-only signals.

Key invariants
--------------
- A benign relationship/love/connection question must NOT receive unsolicited
  self-harm content → action=``exclude``.
- An explicit safety/mental-health question must NOT be blocked by self-harm
  detection → action=``allow_with_context``.
- An event-dependent clip (pandemic, retreat context) must be marked
  ``event_bound`` for a non-event query → action=``exclude``.
- A cross-turn reference (host-turn bleed, orphan opener) must be marked
  ``cross_turn`` → action=``needs_review``.

Design constraints
------------------
- No LLM calls, no network calls, no Qdrant reads.
- Fail-closed: any exception inside a detector returns ``exclude``.
- Called through the shared ``FirstPersonEvidencePolicy`` facade; it remains
  one deterministic gate and does not replace crisis, rights, speaker, or
  relevance decisions.
- All regex patterns are imported from ``first_person_evidence_policy`` so
  the vocabulary stays consistent.
"""

from __future__ import annotations

import re
from typing import Final

from domain.first_person_safety import (
    SAFETY_POLICY_VERSION,
    ContextualSafetyDecision,
    SafetyCategory,
    SafetyDimension,
    SafetySignalType,
)

# ---------------------------------------------------------------------------
# Import existing regex constants from the shared evidence policy module.
# Only module-level constants are imported; no functions that may import
# heavier dependencies (app.config, ingest.*, guardrails.*).
# ---------------------------------------------------------------------------
from services.first_person_evidence_policy import (
    _CORE_WISDOM_KEYWORDS_RE,
    _DANGLING_QUESTION_TAIL_RE,
    _DISCOURSE_ACKNOWLEDGMENT_RE,
    _EVENT_MARKER_RE,
    _HEALTH_CLAIM_RE,
    _ORPHAN_OPENER_RE,
    _SELF_HARM_CLIP_RE,
)

# ---------------------------------------------------------------------------
# Additional local constants
# ---------------------------------------------------------------------------

# Queries that are explicitly about mental-health / safety / self-harm topics.
# When a query touches these topics, self-harm content in a candidate may be
# educational rather than unsolicited.
_MENTAL_HEALTH_QUERY_RE: Final = re.compile(
    r"\b(?:"
    r"suicid\w*"
    r"|self[\s\-]harm"
    r"|mental\s+health"
    r"|depression"
    r"|anxiety"
    r"|therapy"
    r"|therapist"
    r"|counseling"
    r"|counselling"
    r"|psychiatric"
    r"|emotional\s+(?:health|wellbeing|wellness)"
    r")\b",
    re.IGNORECASE,
)

# Benign-topic queries: love, peace, joy, connection, relationships — topics
# that should NEVER surface unsolicited self-harm clips.
_BENIGN_TOPIC_QUERY_RE: Final = re.compile(
    r"\b(?:"
    r"love"
    r"|peace"
    r"|joy"
    r"|happiness"
    r"|connection"
    r"|gratitude"
    r"|compassion"
    r"|kindness"
    r"|relationship"
    r"|relationships"
    r"|togetherness"
    r"|harmony"
    r")\b",
    re.IGNORECASE,
)

# Outcome-promise patterns in candidate text (standalone; no query scope).
_OUTCOME_PROMISE_RE: Final = re.compile(
    r"\b(?:"
    r"guaranteed?\s+to"
    r"|will\s+definitely"
    r"|100\s*%\s+(?:sure|certain|guaranteed?)"
    r"|promise\s+(?:you|that)\s+(?:this|it)\s+will"
    r"|you\s+will\s+(?:always|never\s+again|be\s+completely)"
    r")\b",
    re.IGNORECASE,
)

# Cross-turn: a short orphan-opener clip that also begins with a discourse
# acknowledgment is very likely host-turn bleed.
_SHORT_CLIP_THRESHOLD: Final = 40  # words


def _is_short(text: str) -> bool:
    return len(text.split()) < _SHORT_CLIP_THRESHOLD


class FirstPersonSafetyPolicy:
    """Contextual safety evaluation returning structured SafetyDimensions.

    Distinguishes query-context from candidate-only signals.
    All detectors are deterministic; no LLM calls.
    Fail-closed: on any exception, returns an ``exclude`` decision.
    """

    POLICY_VERSION: Final[str] = SAFETY_POLICY_VERSION

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        *,
        query: str,
        candidate_text: str,
        context_text: str = "",  # bounded context window if available
    ) -> ContextualSafetyDecision:
        """Evaluate query + candidate + context for safety dimensions.

        Returns a :class:`ContextualSafetyDecision` with zero or more
        :class:`SafetyDimension` objects.  The most severe ``action`` across
        all triggered dimensions wins; precedence is::

            exclude > needs_review > allow_with_context > allow
        """
        try:
            return self._evaluate_inner(
                query=query,
                candidate_text=candidate_text,
                context_text=context_text,
            )
        except Exception:  # noqa: BLE001
            # Fail-closed on any unexpected detector error.
            return ContextualSafetyDecision(
                action="exclude",
                dimensions=(),
                reason_codes=("detector_exception",),
                policy_version=self.POLICY_VERSION,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate_inner(
        self,
        *,
        query: str,
        candidate_text: str,
        context_text: str,
    ) -> ContextualSafetyDecision:
        dimensions: list[SafetyDimension] = []
        reason_codes: list[str] = []

        # ---- Self-harm detectors (query-aware) -------------------------
        if _SELF_HARM_CLIP_RE.search(candidate_text):
            if _MENTAL_HEALTH_QUERY_RE.search(query):
                # Query explicitly concerns mental health / safety → educational
                dimensions.append(
                    SafetyDimension(
                        category=SafetyCategory.SELF_HARM,
                        signal_type=SafetySignalType.EDUCATION,
                        confidence=0.85,
                        detector="self_harm_educational_detector",
                        policy_version=self.POLICY_VERSION,
                    )
                )
                reason_codes.append("self_harm_educational_context")
            elif _BENIGN_TOPIC_QUERY_RE.search(query) or not query.strip():
                # Benign query: self-harm content is unsolicited → exclude
                dimensions.append(
                    SafetyDimension(
                        category=SafetyCategory.UNSOLICITED_SENSITIVE,
                        signal_type=SafetySignalType.MENTION,
                        confidence=1.0,
                        detector="self_harm_unsolicited_detector",
                        policy_version=self.POLICY_VERSION,
                    )
                )
                reason_codes.append("unsolicited_self_harm_reference")
            else:
                # No query-topic signal but clip contains self-harm → exclude
                dimensions.append(
                    SafetyDimension(
                        category=SafetyCategory.UNSOLICITED_SENSITIVE,
                        signal_type=SafetySignalType.MENTION,
                        confidence=1.0,
                        detector="self_harm_unsolicited_detector",
                        policy_version=self.POLICY_VERSION,
                    )
                )
                reason_codes.append("unsolicited_self_harm_reference")

        # ---- Event marker detector (candidate-only) --------------------
        if _EVENT_MARKER_RE.search(candidate_text) or (
            context_text and _EVENT_MARKER_RE.search(context_text)
        ):
            dimensions.append(
                SafetyDimension(
                    category=SafetyCategory.EVENT_BOUND,
                    signal_type=SafetySignalType.EVENT_DEP,
                    confidence=1.0,
                    detector="event_marker_detector",
                    policy_version=self.POLICY_VERSION,
                )
            )
            reason_codes.append("event_bound")

        # ---- Health-claim detector (candidate-only) --------------------
        if _HEALTH_CLAIM_RE.search(candidate_text):
            dimensions.append(
                SafetyDimension(
                    category=SafetyCategory.MEDICAL_CLAIM,
                    signal_type=SafetySignalType.MENTION,
                    confidence=1.0,
                    detector="health_claim_detector",
                    policy_version=self.POLICY_VERSION,
                )
            )
            reason_codes.append("health_claim")

        # ---- Outcome-promise detector (candidate-only) -----------------
        if _OUTCOME_PROMISE_RE.search(candidate_text):
            dimensions.append(
                SafetyDimension(
                    category=SafetyCategory.OUTCOME_PROMISE,
                    signal_type=SafetySignalType.MENTION,
                    confidence=0.9,
                    detector="outcome_promise_detector",
                    policy_version=self.POLICY_VERSION,
                )
            )
            reason_codes.append("outcome_promise")

        # ---- Dangling question tail (candidate-only) -------------------
        # Only explicit open/dependent forms are a dangling dependency. A
        # complete rhetorical question is not evidence of a missing antecedent;
        # question-only clips are handled by the harness's dedicated gate.
        stripped = candidate_text.rstrip()
        if _DANGLING_QUESTION_TAIL_RE.search(stripped):
            dimensions.append(
                SafetyDimension(
                    category=SafetyCategory.DANGLING_DEPENDENCY,
                    signal_type=SafetySignalType.MENTION,
                    confidence=0.9,
                    detector="dangling_question_tail_detector",
                    policy_version=self.POLICY_VERSION,
                )
            )
            reason_codes.append("dangling_dependency")

        # ---- Orphan opener (candidate-only) → dangling_dependency ------
        if _ORPHAN_OPENER_RE.match(candidate_text) and not _CORE_WISDOM_KEYWORDS_RE.search(candidate_text):
            dimensions.append(
                SafetyDimension(
                    category=SafetyCategory.DANGLING_DEPENDENCY,
                    signal_type=SafetySignalType.MENTION,
                    confidence=0.85,
                    detector="orphan_opener_detector",
                    policy_version=self.POLICY_VERSION,
                )
            )
            reason_codes.append("dangling_dependency")

        # ---- Cross-turn reference (candidate-only) ---------------------
        # A discourse acknowledgment opener on a short clip is likely host-turn
        # bleed; treat as cross_turn_reference → needs_review.
        if _DISCOURSE_ACKNOWLEDGMENT_RE.match(candidate_text) and _is_short(candidate_text):
            dimensions.append(
                SafetyDimension(
                    category=SafetyCategory.CROSS_TURN_REFERENCE,
                    signal_type=SafetySignalType.CROSS_TURN,
                    confidence=0.8,
                    detector="cross_turn_discourse_detector",
                    policy_version=self.POLICY_VERSION,
                )
            )
            reason_codes.append("cross_turn_reference")

        # ---- Determine winning action ----------------------------------
        action = self._resolve_action(dimensions)

        return ContextualSafetyDecision(
            action=action,
            dimensions=tuple(dimensions),
            reason_codes=tuple(dict.fromkeys(reason_codes)),  # deduplicate, preserve order
            policy_version=self.POLICY_VERSION,
        )

    @staticmethod
    def _resolve_action(
        dimensions: list[SafetyDimension],
    ) -> str:
        """Return the most severe action across all dimensions.

        Precedence: exclude > needs_review > allow_with_context > allow.
        """
        if not dimensions:
            return "allow"

        categories_to_action = {
            SafetyCategory.UNSOLICITED_SENSITIVE: "exclude",
            SafetyCategory.MEDICAL_CLAIM: "exclude",
            SafetyCategory.OUTCOME_PROMISE: "exclude",
            SafetyCategory.EVENT_BOUND: "exclude",
            SafetyCategory.VIOLENCE: "exclude",
            SafetyCategory.SEXUAL_CONTENT: "exclude",
            SafetyCategory.SELF_HARM: None,  # resolved by signal_type below
            SafetyCategory.DANGLING_DEPENDENCY: "needs_review",
            SafetyCategory.CROSS_TURN_REFERENCE: "needs_review",
        }

        result = "allow"
        _precedence = {"exclude": 3, "needs_review": 2, "allow_with_context": 1, "allow": 0}

        for dim in dimensions:
            mapped = categories_to_action.get(dim.category)
            if mapped is None and dim.category == SafetyCategory.SELF_HARM:
                # Self-harm: educational → allow_with_context; anything else → exclude
                mapped = (
                    "allow_with_context"
                    if dim.signal_type == SafetySignalType.EDUCATION
                    else "exclude"
                )
            if mapped and _precedence.get(mapped, 0) > _precedence.get(result, 0):
                result = mapped

        return result


# Module-level singleton, consistent with first_person_evidence_policy pattern.
first_person_safety_policy = FirstPersonSafetyPolicy()


if __name__ == "__main__":
    _policy = FirstPersonSafetyPolicy()

    # Benign love query + self-harm clip → exclude
    _d1 = _policy.evaluate(
        query="How do I experience more love in my life?",
        candidate_text="When someone is suicidal they often withdraw from friends.",
    )
    assert _d1.action == "exclude", f"Expected exclude, got {_d1.action}"
    assert "unsolicited_self_harm_reference" in _d1.reason_codes

    # Explicit mental-health query + educational self-harm content → allow_with_context
    _d2 = _policy.evaluate(
        query="How do I support someone who is suicidal?",
        candidate_text="Self-harm is a sign of deep inner pain that needs attention.",
    )
    assert _d2.action == "allow_with_context", f"Expected allow_with_context, got {_d2.action}"

    # Pandemic clip + general query → exclude (event_bound)
    _d3 = _policy.evaluate(
        query="How do I find peace?",
        candidate_text="During the covid lockdown, many people struggled with isolation.",
    )
    assert _d3.action == "exclude"
    assert _d3.is_event_bound

    # Clean clip + benign query → allow
    _d4 = _policy.evaluate(
        query="What is the nature of inner peace?",
        candidate_text="Inner peace arises naturally when the mind stops its chatter.",
    )
    assert _d4.action == "allow"
    assert _d4.may_serve

    print("first_person_safety_policy self-check passed")
