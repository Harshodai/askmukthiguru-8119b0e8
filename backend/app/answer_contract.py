"""Answer contract helpers (NEW-ANS-2; spec SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT §3.6).

Pure functions only: no I/O, no text from the seeker, no LLM.
"""

from __future__ import annotations

# Reasons that mean "the check could not run", not "no teaching was found".
_SYSTEM_REASONS = frozenset(
    {
        "relevance_indeterminate",
        "serving_contract_violation",
        "store_unavailable",
        "quote_contract_violation",
        "output_rail_unavailable",
    }
)
_TOPIC_REASONS = frozenset({"topic_blocked"})

ABSTAIN_CAUSES = ("no_evidence", "system_unavailable", "topic_boundary", "safety")


def abstain_cause(status: str | None, reason: str | None, answerability: str | None) -> str:
    """Map the pipeline's status, abstain reason and gate verdict to one cause.

    ``system_unavailable`` is the only cause for which ``verification.passed``
    is false: the seeker was not told the truth that no teaching exists, only
    that the check failed. Unknown reasons fall to ``no_evidence`` only when the
    status is not an error.
    """
    status = str(status or "").strip().lower()
    reason = str(reason or "").strip().lower()
    verdict = str(answerability or "").strip().lower()
    if status == "error" or reason in _SYSTEM_REASONS:
        return "system_unavailable"
    if reason == "answerability_withheld" and verdict not in ("no", ""):
        return "system_unavailable"
    if reason in _TOPIC_REASONS:
        return "topic_boundary"
    return "no_evidence"


def abstain_copy_key(cause: str) -> str:
    """Static copy key for a cause (keys only; copy and review are NEW-ANS-4)."""
    return f"abstain.{cause}"
