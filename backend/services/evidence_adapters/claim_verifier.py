"""Deterministic Claim, Quotation, and Attribution Verifier."""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache

from domain.evidence_contract import (
    ClaimEvidenceMapping,
    ClaimVerificationReport,
    EpistemicCategory,
    EvidenceCandidate,
)
from services.guru_registry import get_gurus, label_for, shared_attribution

_WS_RE = re.compile(r"\s+")
_PUNCT_EDGE_RE = re.compile(r"^[\W_]+|[\W_]+$")


@lru_cache(maxsize=1)
def _teacher_aliases() -> dict[str, set[str]]:
    """Canonical teacher id -> accepted spellings, derived from the guru registry."""
    aliases: dict[str, set[str]] = {}
    for g in get_gurus():
        label = g.label.lower()
        # bare first-name stem ("<name>ji" -> "<name>") was always accepted
        stem = g.id.removesuffix("ji")
        aliases[g.id] = {g.id, label, label.replace(" ", "_"), label.replace(" ", "-"), stem}
    primary, shared_ids = shared_attribution()
    if primary:
        labels = [label_for(i).lower() for i in shared_ids if label_for(i)]
        aliases[primary] = {
            primary,
            " & ".join(labels),
            " and ".join(labels),
            "both",
            "shared",
        }
    return aliases


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").lower()).strip()


def _canon_teacher(val: str | None) -> str | None:
    if not val:
        return None
    low = _norm(val)
    for canon, aliases in _teacher_aliases().items():
        if low in aliases or low == canon:
            return canon
    return low


def _teachers_compatible(attributed: str | None, evidence_teacher: str | None) -> bool:
    c_attr = _canon_teacher(attributed)
    c_ev = _canon_teacher(evidence_teacher)
    if not c_attr or not c_ev:
        return c_attr == c_ev
    if c_attr == c_ev:
        return True
    primary, shared_ids = shared_attribution()
    if c_ev == primary and c_attr in shared_ids:
        return True
    return c_attr == primary and c_ev in shared_ids


class ClaimVerificationService:
    """Verifies exact quotations, teacher attributions, and version freshness against evidence."""

    def verify_claims(
        self,
        claims: Iterable[ClaimEvidenceMapping],
        evidence_pool: Iterable[EvidenceCandidate],
        *,
        expected_source_versions: dict[str, str] | None = None,
    ) -> ClaimVerificationReport:
        by_id: dict[str, EvidenceCandidate] = {c.evidence_id: c for c in evidence_pool}
        results: list[ClaimEvidenceMapping] = []
        unsupported = 0
        misattributed = 0
        quote_mismatch = 0
        outdated = 0

        for claim in claims:
            if (
                claim.epistemic_category
                in {
                    EpistemicCategory.INTERPRETATION,
                    EpistemicCategory.APPLICATION,
                    EpistemicCategory.EDITORIAL_NARRATION,
                }
                and not claim.teacher_attributed
            ):
                results.append(claim.model_copy(update={"verification_status": "ai_labeled"}))
                continue

            if not claim.evidence_ids:
                unsupported += 1
                results.append(
                    claim.model_copy(
                        update={
                            "verification_status": "unsupported",
                            "notes": "No supporting evidence_id attached.",
                        }
                    )
                )
                continue

            matched = [by_id[eid] for eid in claim.evidence_ids if eid in by_id]
            if not matched:
                unsupported += 1
                results.append(
                    claim.model_copy(
                        update={
                            "verification_status": "unverifiable",
                            "notes": "Referenced evidence_id(s) not found in verified pool.",
                        }
                    )
                )
                continue

            if expected_source_versions:
                stale = [
                    ev
                    for ev in matched
                    if ev.source_id in expected_source_versions
                    and ev.source_version != expected_source_versions[ev.source_id]
                ]
                if stale:
                    outdated += 1
                    results.append(
                        claim.model_copy(
                            update={
                                "verification_status": "outdated_version",
                                "notes": f"Evidence version mismatch on {[s.evidence_id for s in stale]}",
                            }
                        )
                    )
                    continue

            if claim.teacher_attributed and not any(
                _teachers_compatible(claim.teacher_attributed, ev.teacher_id) for ev in matched
            ):
                misattributed += 1
                results.append(
                    claim.model_copy(
                        update={
                            "verification_status": "misattributed",
                            "notes": (
                                f"Attributed to {claim.teacher_attributed!r}, but evidence belongs to "
                                f"{[ev.teacher_id for ev in matched]}"
                            ),
                        }
                    )
                )
                continue

            if claim.epistemic_category == EpistemicCategory.VERBATIM_EVIDENCE:
                if not claim.teacher_attributed:
                    unsupported += 1
                    results.append(
                        claim.model_copy(
                            update={
                                "verification_status": "unsupported",
                                "notes": "Exact quote requires an attributed teacher.",
                            }
                        )
                    )
                    continue
                # Only Qdrant-sourced spans with a verified speaker can back an exact quote:
                # OKF is LLM-extracted summary (CLAUDE.md invariant 12) and graph rows are not
                # speaker-verified clips. Field used: EvidenceCandidate.speaker_verified is True.
                matched = [
                    ev
                    for ev in matched
                    if ev.retrieval_source == "qdrant" and ev.speaker_verified is True
                ]
                if not matched:
                    quote_mismatch += 1
                    results.append(
                        claim.model_copy(
                            update={
                                "verification_status": "quote_mismatch",
                                "notes": (
                                    "Exact quote requires a Qdrant span with a verified speaker; "
                                    "OKF, Memgraph and unverified-speaker evidence are not verbatim."
                                ),
                            }
                        )
                    )
                    continue
                q_norm = _PUNCT_EDGE_RE.sub("", _norm(claim.claim_text))
                if not q_norm or not any(
                    q_norm in _norm(f"{ev.text} {ev.surrounding_context or ''}") for ev in matched
                ):
                    quote_mismatch += 1
                    results.append(
                        claim.model_copy(
                            update={
                                "verification_status": "quote_mismatch",
                                "notes": "Direct quotation text does not match canonical source verbatim.",
                            }
                        )
                    )
                    continue

            results.append(
                claim.model_copy(
                    update={
                        "verification_status": "verified",
                        "notes": "Verified against canonical evidence.",
                    }
                )
            )

        passed = unsupported == 0 and misattributed == 0 and quote_mismatch == 0 and outdated == 0
        return ClaimVerificationReport(
            passed=passed,
            mappings=results,
            unsupported_count=unsupported,
            misattributed_count=misattributed,
            quote_mismatch_count=quote_mismatch,
            outdated_version_count=outdated,
            summary=(
                "All claims verified."
                if passed
                else f"Failed: unsupported={unsupported}, misattributed={misattributed}, "
                f"quote_mismatch={quote_mismatch}, outdated={outdated}"
            ),
        )
