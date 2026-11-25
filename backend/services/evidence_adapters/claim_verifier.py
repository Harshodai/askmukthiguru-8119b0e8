"""Deterministic Claim, Quotation, and Attribution Verifier."""

from __future__ import annotations

import re
from collections.abc import Iterable

from domain.evidence_contract import (
    ClaimEvidenceMapping,
    ClaimVerificationReport,
    EpistemicCategory,
    EvidenceCandidate,
)

_WS_RE = re.compile(r"\s+")
_PUNCT_EDGE_RE = re.compile(r"^[\W_]+|[\W_]+$")

_TEACHER_ALIASES: dict[str, set[str]] = {
    "preethaji": {"preethaji", "sri preethaji", "sri_preethaji", "sri-preethaji", "preetha"},
    "krishnaji": {"krishnaji", "sri krishnaji", "sri_krishnaji", "sri-krishnaji", "krishna"},
    "preethaji_krishnaji": {
        "preethaji_krishnaji",
        "sri preethaji & sri krishnaji",
        "sri preethaji and sri krishnaji",
        "both",
        "shared",
    },
}


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").lower()).strip()


def _canon_teacher(val: str | None) -> str | None:
    if not val:
        return None
    low = _norm(val)
    for canon, aliases in _TEACHER_ALIASES.items():
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
    if c_ev == "preethaji_krishnaji" and c_attr in {"preethaji", "krishnaji"}:
        return True
    if c_attr == "preethaji_krishnaji" and c_ev in {"preethaji", "krishnaji"}:
        return True
    return False


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
                            "verification_status": "unsupported",
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
