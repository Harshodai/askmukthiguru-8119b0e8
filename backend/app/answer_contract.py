"""Answer contract helpers (NEW-ANS-2; spec SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT §3.6).

Pure functions only: no I/O, no text from the seeker, no LLM.
"""

from __future__ import annotations

from typing import Any

# Reasons that mean "the check could not run", not "no teaching was found".
_SYSTEM_REASONS = frozenset(
    {
        "relevance_indeterminate",
        "serving_contract_violation",
        "store_unavailable",
        "quote_contract_violation",
        "output_rail_unavailable",
        "served_integrity_failure",
    }
)
_TOPIC_REASONS = frozenset({"topic_blocked"})

# ``result.error`` prefixes that mean the retrieval backend failed (not "no clip").
_SYSTEM_ERROR_PREFIXES = ("context_retrieval_error:",)

ABSTAIN_CAUSES = ("no_evidence", "system_unavailable", "topic_boundary", "safety")


def abstain_cause(
    status: str | None,
    reason: str | None,
    answerability: str | None,
    error: str | None = None,
) -> str:
    """Map the pipeline's status, abstain reason and gate verdict to one cause.

    ``system_unavailable`` is the only cause for which ``verification.passed``
    is false: the seeker was not told the truth that no teaching exists, only
    that the check failed. Unknown reasons fall to ``no_evidence`` only when the
    status is not an error. A retrieval outage (``error`` starting with a
    ``_SYSTEM_ERROR_PREFIXES`` entry) is also ``system_unavailable``.
    """
    status = str(status or "").strip().lower()
    reason = str(reason or "").strip().lower()
    verdict = str(answerability or "").strip().lower()
    if str(error or "").startswith(_SYSTEM_ERROR_PREFIXES):
        return "system_unavailable"
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


def served_clip_integrity_failures(citations: list[dict], answer: str) -> list[str]:
    """Re-check every served clip at response assembly (NEW-SEC-1, OPS-002).

    Returns the failed checks (``hash``, ``substring``), one entry per failure.
    The serve gate already quarantines a clip whose text no longer matches its
    hash; this is the second line for a gate that was bypassed (a cache entry,
    a new code path). ``source_text_hash`` is the v10 per-span field
    (invariant 2); a legacy clip without it is checked against
    ``transcript_hash``. A clip with neither hash fails.
    """
    import hashlib

    failures: list[str] = []
    for citation in citations or []:
        if not isinstance(citation, dict):
            failures.append("hash")
            continue
        text = str(citation.get("verbatim_text") or "")
        expected = str(citation.get("source_text_hash") or citation.get("transcript_hash") or "")
        if not text.strip() or hashlib.sha256(text.encode("utf-8")).hexdigest() != expected:
            failures.append("hash")
        if text.strip() and text.strip() not in (answer or ""):
            failures.append("substring")
    return failures


def build_public_answer_fields(result: Any) -> dict[str, Any]:
    """Build unified public response fields ensuring wire parity across sync, queued and SSE writers (PROD-CQ-02)."""
    from dataclasses import asdict, is_dataclass

    answer_evidence = getattr(result, "answer_evidence", None)
    guidance_plan = getattr(result, "guidance_plan", None)

    def _to_dict_safe(obj: Any) -> Any:
        if obj is None:
            return None
        if is_dataclass(obj):
            return asdict(obj)
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        return obj

    route_meta = getattr(result, "route_metadata", {}) or {}
    safety_notices = list(
        route_meta.get("safety_notices") or getattr(result, "safety_notices", []) or []
    )

    return {
        "intent": getattr(result, "intent", None),
        "meditation_step": getattr(result, "meditation_step", 0),
        "proactive_serene_mind": getattr(result, "proactive_serene_mind", None),
        "trace_id": getattr(result, "trace_id", None),
        "latency_ms": getattr(result, "latency_ms", None),
        "model_used": getattr(result, "model_used", None),
        "model_provider": getattr(result, "model_provider", None),
        "route_decision": getattr(result, "route_decision", None),
        "query_tier": getattr(result, "query_tier", None),
        "cache_hit": getattr(result, "cache_hit", False),
        "faithfulness_score": getattr(result, "faithfulness_score", None),
        "relevancy_score": getattr(result, "relevancy_score", None),
        "confidence_score": getattr(result, "confidence_score", None),
        "hallucination_flag": getattr(result, "hallucination_flag", None),
        "follow_up_suggestions": getattr(result, "follow_up_suggestions", []) or [],
        "citations_verified": getattr(result, "citations_verified", None),
        "orphan_citations_stripped": getattr(result, "orphan_citations_stripped", None),
        "live_logistics_events": getattr(result, "live_logistics_events", []) or [],
        "answer_evidence": _to_dict_safe(answer_evidence),
        "guidance_plan": _to_dict_safe(guidance_plan),
        "safety_notices": safety_notices,
        "verification": getattr(result, "verification", None),
        "route_metadata": route_meta,
    }
