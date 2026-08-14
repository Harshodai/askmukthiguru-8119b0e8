from __future__ import annotations

from typing import Any, Literal

GroundingState = Literal["grounded", "abstained", "safety_redirect", "system_error"]


def grounding_state_for(result: Any) -> GroundingState:
    """Derive a conservative, user-visible grounding state from pipeline output.

    A response is only labelled grounded when it has at least one retrieved
    source and citations were not explicitly marked unverified. Safety and
    blocked responses remain separate from ordinary abstention. This helper is
    intentionally conservative: an unknown or incomplete evidence envelope is
    never promoted to a grounded claim.
    """
    if getattr(result, "blocked", False):
        return "safety_redirect"

    intent = str(getattr(result, "intent", "") or "").upper()
    if intent in {"CRISIS", "SAFETY", "SELF_HARM", "DISTRESS_SAFETY"}:
        return "safety_redirect"

    evidence = getattr(result, "answer_evidence", None)
    source_count = getattr(evidence, "source_count", None)
    if source_count is None and isinstance(evidence, dict):
        source_count = evidence.get("source_count")
    if source_count is None:
        source_count = len(getattr(result, "citations", None) or [])

    citations_verified = getattr(result, "citations_verified", None)
    hallucination_flag = bool(getattr(result, "hallucination_flag", False))
    if int(source_count or 0) > 0 and citations_verified is not False and not hallucination_flag:
        return "grounded"
    return "abstained"
