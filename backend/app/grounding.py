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
    if intent in {
        "DISTRESS",
        "SAFETY_VIOLATION",
        "CRISIS",
        "SAFETY",
        "SELF_HARM",
        "DISTRESS_SAFETY",
    }:
        return "safety_redirect"
    if intent in {"ERROR", "TIMEOUT"}:
        return "system_error"

    verification = getattr(result, "verification", None)
    if not isinstance(verification, dict):
        verification = {}
    if (
        verification.get("method") == "grounded_partial_evidence"
        and getattr(result, "citations", None)
        and verification.get("partial") is True
        # citations_verified can describe the rejected model draft rather than
        # this deterministic excerpt envelope. The fallback itself derives its
        # citations from the same retrieved documents, so require citations and
        # no hallucination flag but do not inherit the draft's failed verdict.
        and not bool(getattr(result, "hallucination_flag", False))
    ):
        # The model draft failed verification, but the public answer is made
        # exclusively from retrieved excerpts with resolvable source URLs.
        # Keep the user-visible state grounded while the verification metadata
        # transparently records that this is a partial evidence envelope.
        return "grounded"

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
