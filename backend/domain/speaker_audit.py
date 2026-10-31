"""Random listen audit of auto-verified speaker spans (P6) and the gate that reads it.

Automated verification can be wrong in a way no score shows (a host voice that sounds like
the teacher, a mis-pinned calibration). A person listening to a random sample is the only
check that does not share the verifier's blind spots. This module draws that sample and
turns the listeners' answers into a promotion decision.

* **Reproducible.** The sample is a pure function of ``(seed, batch_id, pool)``. Spans are
  ranked by ``sha256(seed|batch_id|span_id)``, so it does not depend on Python's ``random``
  implementation and a second run draws the same spans.
* **Fixed size.** ``max(30, ceil(5%))`` of each stratum, capped at the stratum size. These
  numbers are an opinion from the merged plan (2026-10-31), not a measured requirement.
* **Humans are audited too.** Spans verified by ``human_listen_v1`` form their own stratum
  and are sampled by the same rule (plan I4, condition 7).
* **Stop rule.** One human answer "not the teacher" on an audited span blocks the batch.
  A sampled span nobody has answered, or answered ``unclear``, also blocks it: an audit
  that was not finished is not an audit.

Stdlib only; works on raw payload dicts.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Mapping
from typing import Any

from domain.speaker_provenance import (
    CONFIRMING_CHOICE,
    KNOWN_METHODS,
    METHOD_ECAPA_CENTROID_V1,
    METHOD_HUMAN_LISTEN_V1,
    REVIEW_CHOICES,
    speaker_write_violations,
)

AUDIT_MIN_SPANS = 30
AUDIT_FRACTION = 0.05

STRATUM_AUTOMATED = "automated"
STRATUM_HUMAN = "human"

DECISION_PASS = "pass"
DECISION_BLOCKED_NOT_TEACHER = "blocked_not_teacher"
DECISION_BLOCKED_INCOMPLETE = "blocked_incomplete"

#: The review choice that confirms each labelled teacher.
_CONFIRMING_CHOICE = CONFIRMING_CHOICE
_NOT_TEACHER_CHOICES = frozenset(REVIEW_CHOICES) - {"unclear"}


def audit_sample_size(
    pool_size: int, *, minimum: int = AUDIT_MIN_SPANS, fraction: float = AUDIT_FRACTION
) -> int:
    """``max(minimum, ceil(fraction * pool))``, never more than the pool."""
    if pool_size <= 0:
        return 0
    return min(pool_size, max(int(minimum), math.ceil(fraction * pool_size)))


def audit_pools(payloads: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    """Verified child spans with a recognised method, split into automated and human strata."""
    pools: dict[str, list[Mapping[str, Any]]] = {STRATUM_AUTOMATED: [], STRATUM_HUMAN: []}
    for payload in payloads:
        if payload.get("record_type") not in (None, "retrieval_child"):
            continue
        if payload.get("speaker_verified") is not True or not payload.get("source_span_id"):
            continue
        method = str(payload.get("voice_verification_method") or "")
        if method not in KNOWN_METHODS:
            continue
        stratum = STRATUM_HUMAN if method == METHOD_HUMAN_LISTEN_V1 else STRATUM_AUTOMATED
        pools[stratum].append(payload)
    return pools


def _rank(seed: str, batch_id: str, span_id: str) -> str:
    return hashlib.sha256(f"{seed}|{batch_id}|{span_id}".encode()).hexdigest()


def draw_audit_sample(
    payloads: Iterable[Mapping[str, Any]],
    *,
    batch_id: str,
    seed: str,
    minimum: int = AUDIT_MIN_SPANS,
    fraction: float = AUDIT_FRACTION,
) -> dict[str, Any]:
    """Draw the audit sample for one ingestion batch. Pure and reproducible."""
    if not str(batch_id).strip() or not str(seed).strip():
        raise ValueError("batch_id and seed must both be non-empty")
    pools = audit_pools(payloads)
    strata: dict[str, Any] = {}
    chosen: list[dict[str, str]] = []
    for name, pool in pools.items():
        unique = {str(p["source_span_id"]): p for p in pool}
        k = audit_sample_size(len(unique), minimum=minimum, fraction=fraction)
        ranked = sorted(unique, key=lambda span_id: (_rank(seed, batch_id, span_id), span_id))
        picked = sorted(ranked[:k])
        strata[name] = {"pool": len(unique), "sampled": len(picked)}
        for span_id in picked:
            payload = unique[span_id]
            chosen.append(
                {
                    "source_span_id": span_id,
                    "stratum": name,
                    "video_id": str(payload.get("video_id") or ""),
                    "guru_id": str(payload.get("guru_id") or ""),
                    "method": str(payload.get("voice_verification_method") or ""),
                }
            )
    chosen.sort(key=lambda row: row["source_span_id"])
    digest = hashlib.sha256("\n".join(row["source_span_id"] for row in chosen).encode()).hexdigest()
    return {
        "batch_id": batch_id,
        "seed": seed,
        "minimum": minimum,
        "fraction": fraction,
        "strata": strata,
        "spans": chosen,
        "sample_sha256": digest,
    }


def classify_review(guru_id: str, review_choice: str | None) -> str:
    """``confirmed``, ``not_teacher`` or ``unresolved`` for one blind listening answer."""
    if not review_choice or review_choice == "unclear":
        return "unresolved"
    confirming = _CONFIRMING_CHOICE.get(guru_id)
    if confirming is not None and review_choice == confirming:
        return "confirmed"
    if review_choice in _NOT_TEACHER_CHOICES:
        return "not_teacher"
    return "unresolved"  # a value outside the vocabulary is never a confirmation


def audit_gate(
    sample: Mapping[str, Any], reviews: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Promotion decision for a batch from its sample and the listeners' answers.

    ``reviews`` maps ``source_span_id`` to a record with ``review_choice``. If a span has
    several answers the caller passes the latest; a conflict that needs a second reviewer
    (plan I4, condition 6) is the caller's to resolve before it gets here.
    """
    confirmed: list[str] = []
    not_teacher: list[str] = []
    unresolved: list[str] = []
    sampled_ids = {row["source_span_id"] for row in sample["spans"]}
    for row in sample["spans"]:
        span_id = row["source_span_id"]
        record = reviews.get(span_id)
        verdict = classify_review(row.get("guru_id", ""), (record or {}).get("review_choice"))
        {"confirmed": confirmed, "not_teacher": not_teacher, "unresolved": unresolved}[
            verdict
        ].append(span_id)
    unknown_reviews = sorted(set(reviews) - sampled_ids)
    if not_teacher:
        decision = DECISION_BLOCKED_NOT_TEACHER
    elif unresolved or not sample["spans"]:
        decision = DECISION_BLOCKED_INCOMPLETE
    else:
        decision = DECISION_PASS
    return {
        "decision": decision,
        "ok": decision == DECISION_PASS,
        "batch_id": sample["batch_id"],
        "sample_sha256": sample["sample_sha256"],
        "sampled": len(sample["spans"]),
        "confirmed": len(confirmed),
        "not_teacher_span_ids": sorted(not_teacher),
        "unresolved_span_ids": sorted(unresolved),
        "reviews_for_spans_outside_the_sample": unknown_reviews,
        "action": {
            DECISION_PASS: "batch may be promoted",
            DECISION_BLOCKED_NOT_TEACHER: (
                "do not promote; a listener rejected an auto-verified span; recalibrate"
            ),
            DECISION_BLOCKED_INCOMPLETE: ("do not promote; finish listening to every sampled span"),
        }[decision],
    }


# --------------------------------------------------------------------------
# Promotion gate over a candidate collection (P4)
# --------------------------------------------------------------------------

PROMOTION_PASS = "pass"
PROMOTION_BLOCKED_EMPTY = "blocked_empty"
PROMOTION_BLOCKED_VIOLATORS = "blocked_violators"
PROMOTION_BLOCKED_AUDIT = "blocked_audit"
PROMOTION_BLOCKED_AUDIT_MISSING = "blocked_audit_missing"

#: A video with at least this many spans, every one verified, is flagged for a human look.
#: The payload cannot say whether a video is Q&A (host questions expected) or a lecture
#: (100% teacher is normal), so this is a flag, never a block. The number is an opinion.
ALL_TEACHER_MIN_SPANS = 10


def promotion_speaker_gate(
    payloads: Iterable[Mapping[str, Any]],
    *,
    audit_gate: Mapping[str, Any] | None = None,
    require_audit_gate: bool = False,
    block_legacy_centroid: bool = False,
    all_teacher_min_spans: int = ALL_TEACHER_MIN_SPANS,
) -> dict[str, Any]:
    """Decide whether a candidate collection may be promoted, on speaker evidence alone.

    Blocks when:

    * the collection has no child spans (an empty build never passes);
    * any child span claims ``speaker_verified=true`` and the write rule refuses it (no
      method, an unknown method, or an automated method with no score, calibration id or
      model revision behind it);
    * a P6 audit result is supplied and is not ``pass``, or none is supplied while
      ``require_audit_gate`` is set.

    Never blocks on: legacy centroid spans (counted; a time-boxed exemption until the v2
    re-score, review 2026-10-31; set ``block_legacy_centroid`` to end it), or the all-teacher
    video flag. Same rule function as ``speaker_provenance_violations`` in the store (a test
    pins that the two agree).

    It evaluates the rule per payload in the caller, which is stricter than a Qdrant filter
    on ``is_empty(voice_verification_method)``: it also catches a method with missing
    provenance. It does not check that audio really produced the score; the P6 audit does.
    """
    children = [p for p in payloads if p.get("record_type") in (None, "retrieval_child")]
    by_method: dict[str, int] = {}
    by_code: dict[str, int] = {}
    violators: list[str] = []
    verified = 0
    per_video: dict[str, list[int]] = {}
    for payload in children:
        is_verified = payload.get("speaker_verified") is True
        verified += is_verified
        counts = per_video.setdefault(str(payload.get("video_id") or "?"), [0, 0])
        counts[0] += 1
        counts[1] += is_verified
        if not is_verified:
            continue
        method = str(payload.get("voice_verification_method") or "") or "none"
        by_method[method] = by_method.get(method, 0) + 1
        # Stored data is READ here: a legacy centroid span is counted below, not refused,
        # unless the time box has ended (`block_legacy_centroid`).
        violations = speaker_write_violations(
            payload, allow_legacy_centroid=not block_legacy_centroid
        )
        if violations:
            violators.append(str(payload.get("source_span_id") or payload.get("id") or "?"))
            for code in {v.split(":", 1)[0] for v in violations}:
                by_code[code] = by_code.get(code, 0) + 1

    audit_ok = (
        None
        if audit_gate is None
        else bool(audit_gate.get("ok") is True and audit_gate.get("decision") == DECISION_PASS)
    )
    if not children:
        decision = PROMOTION_BLOCKED_EMPTY
    elif violators:
        decision = PROMOTION_BLOCKED_VIOLATORS
    elif audit_ok is False:
        decision = PROMOTION_BLOCKED_AUDIT
    elif audit_ok is None and require_audit_gate:
        decision = PROMOTION_BLOCKED_AUDIT_MISSING
    else:
        decision = PROMOTION_PASS

    all_teacher = sorted(
        (
            {"video_id": video, "spans": total}
            for video, (total, ok_count) in per_video.items()
            if total >= all_teacher_min_spans and ok_count == total
        ),
        key=lambda row: (-row["spans"], row["video_id"]),
    )
    return {
        "decision": decision,
        "ok": decision == PROMOTION_PASS,
        "children": len(children),
        "verified": verified,
        "unverified": len(children) - verified,
        "verified_by_method": dict(sorted(by_method.items())),
        "violators": {
            "count": len(violators),
            "by_code": dict(sorted(by_code.items())),
            "span_ids_first_20": sorted(violators)[:20],
        },
        "legacy_centroid_verified": by_method.get(METHOD_ECAPA_CENTROID_V1, 0),
        "audit_gate_checked": audit_ok is not None,
        "audit_gate_decision": None if audit_gate is None else audit_gate.get("decision"),
        "all_teacher_video_flags": {
            "blocking": False,
            "min_spans": all_teacher_min_spans,
            "note": (
                "Flag only. A lecture is 100% teacher by nature; a Q&A video should show "
                "host spans. The payload cannot tell which this is, so a person decides."
            ),
            "videos": all_teacher,
        },
    }
