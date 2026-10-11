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
    # Non-crisis distress runs the full pipeline (it is not a bypass): a cited,
    # verified answer it served is grounded. Only an uncited distress response
    # (e.g. a helpline/redirect message) is a safety redirect.
    if intent == "DISTRESS":
        _verification = getattr(result, "verification", None)
        _method = (
            str((_verification or {}).get("method", "")) if isinstance(_verification, dict) else ""
        )
        _nested_citations_verified = (
            isinstance(_verification, dict) and _verification.get("citations_verified") is True
        )
        _top_citations_verified = getattr(result, "citations_verified", None)
        if (
            "preemption" not in _method
            and getattr(result, "citations", None)
            and (
                _top_citations_verified is not False
                and (_top_citations_verified is True or _nested_citations_verified)
            )
            and (
                not isinstance(_verification, dict)
                or not _verification
                or _verification.get("passed") is True
            )
            and not bool(getattr(result, "hallucination_flag", False))
        ):
            return "grounded"
        return "safety_redirect"
    if intent in {
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
        verification.get("method") == "redacted_unsupported_claims"
        and getattr(result, "citations", None)
        and not bool(getattr(result, "hallucination_flag", False))
    ):
        # Every sentence that survived redaction was grounded by the verifier —
        # the unsupported ones were removed before the answer shipped — so this
        # is a grounded answer, not an abstention. Without this clause a
        # redacted answer fell through to the generic path and was labelled
        # "abstained" while carrying real prose and citations.
        return "grounded"

    # grounded_partial_evidence is deliberately NOT promoted: the model draft failed
    # verification (passed=False) and only retrieved excerpts ship. Publicly that is
    # "abstained" (with citations + verification.partial=true for clients that want
    # the excerpts). Reversed 2026-10-11 from the 2026-08-23 "publicly grounded"
    # decision: a grounded label beside verification.passed=false contradicts itself
    # and misleads every non-web client (WhatsApp, API).

    evidence = getattr(result, "answer_evidence", None)
    source_count = getattr(evidence, "source_count", None)
    if source_count is None and isinstance(evidence, dict):
        source_count = evidence.get("source_count")
    if source_count is None:
        source_count = len(getattr(result, "citations", None) or [])

    citations_verified = getattr(result, "citations_verified", None)
    nested_citations_verified = verification.get("citations_verified") is True
    hallucination_flag = bool(getattr(result, "hallucination_flag", False))
    if (
        int(source_count or 0) > 0
        and (
            citations_verified is not False
            and (citations_verified is True or nested_citations_verified)
        )
        and (not verification or verification.get("passed") is True)
        and not hallucination_flag
    ):
        return "grounded"
    return "abstained"
