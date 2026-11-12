"""One typed decision contract for the first-person serving path.

Each concern has exactly one record and one owner:

- :class:`ContentAssessment` — what the candidate text *is* (clinical claim,
  wellbeing framing, violence discourse, ...). Produced once by
  ``services.first_person_content_assessment``; the serving path reads the
  verdict and never re-derives it with phrase regexes.
- :class:`CoverageDecision` — whether the selected evidence covers the facets
  the question actually asked for. Produced by the facet planner + set
  selector; a missing required facet is an abstain, not a truncation.
- :class:`ServeDecision` — the final posture (direct / related / abstain)
  derived from the two records above plus the pipeline's own status.

Why a contract: the pre-2026-11 serving path recomputed "is this clip
standalone", "is this a health claim", and "is this compound" independently in
the bridge, the evidence policy, the harness, and the store. The three copies
disagreed, so every fix moved the failure to another copy. A frozen record that
is computed once and revalidated (never recomputed) removes that failure mode.

All records are pure data. No I/O, no LLM calls, no regexes here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

DECISION_CONTRACT_VERSION = "first_person_decision_v1"


# ---------------------------------------------------------------------------
# Content assessment
# ---------------------------------------------------------------------------


class AssessmentKind(StrEnum):
    """What a content finding is about.

    The kinds are deliberately disjoint. ``CLINICAL_CLAIM`` and
    ``CAUSAL_ETIOLOGY`` are medical assertions that may not be served;
    ``WELLBEING_FRAMING`` is a spiritual/Ayurvedic framing that may be served
    with platform copy. A text that asserts both is excluded — the more severe
    finding wins, and one text never produces a notice that hides an exclusion.
    """

    CLINICAL_CLAIM = "clinical_claim"
    CAUSAL_ETIOLOGY = "causal_etiology"
    WELLBEING_FRAMING = "wellbeing_framing"
    OUTCOME_PROMISE = "outcome_promise"
    VIOLENCE = "violence"
    GRAPHIC_VIOLENCE = "graphic_violence"
    SELF_HARM = "self_harm"
    EVENT_BOUND = "event_bound"
    DANGLING_DEPENDENCY = "dangling_dependency"
    CROSS_TURN = "cross_turn"
    ATTENDEE_TESTIMONIAL = "attendee_testimonial"
    ASR_GARBAGE = "asr_garbage"
    BOUNDARY = "boundary"
    PRACTICE_INVITATION = "practice_invitation"


class FindingSeverity(StrEnum):
    """How severe a finding is for serving.

    ``EXCLUDE`` may not be served at all. ``REVIEW`` may only be served when a
    reviewer/owner path has approved it. ``NOTICE`` may be served with platform
    copy that is never presented as the teacher's words.
    """

    EXCLUDE = "exclude"
    REVIEW = "review"
    NOTICE = "notice"


_SEVERITY_ORDER: Mapping[FindingSeverity, int] = {
    FindingSeverity.NOTICE: 1,
    FindingSeverity.REVIEW: 2,
    FindingSeverity.EXCLUDE: 3,
}


@dataclass(frozen=True, slots=True)
class ContentFinding:
    """One deterministic finding about candidate or query text.

    ``code`` is a bounded snake_case vocabulary token that travels into
    ``reason_codes`` and audit records. ``detector`` names the detector for
    auditability and must never contain user prose or candidate text.
    """

    code: str
    kind: AssessmentKind
    severity: FindingSeverity
    detector: str
    confidence: float = 1.0
    contract_version: str = DECISION_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class ContentAssessment:
    """Complete content verdict for one text (or one context window).

    ``degraded`` is True when the assessor could not run to completion. A
    degraded assessment fails closed: it may not be served as a direct answer.
    """

    findings: tuple[ContentFinding, ...] = ()
    degraded: bool = False
    contract_version: str = DECISION_CONTRACT_VERSION

    @property
    def may_serve(self) -> bool:
        """True only when nothing argues against serving at all."""
        return not self.degraded and not any(
            f.severity is FindingSeverity.EXCLUDE for f in self.findings
        )

    @property
    def requires_review(self) -> bool:
        return any(f.severity is FindingSeverity.REVIEW for f in self.findings)

    @property
    def severity(self) -> FindingSeverity | None:
        """Most severe finding, or None when the text is clean."""
        if self.degraded:
            return FindingSeverity.EXCLUDE
        if not self.findings:
            return None
        return max(self.findings, key=lambda f: _SEVERITY_ORDER[f.severity]).severity

    @property
    def exclusion_codes(self) -> tuple[str, ...]:
        return _dedupe(f.code for f in self.findings if f.severity is FindingSeverity.EXCLUDE)

    @property
    def review_codes(self) -> tuple[str, ...]:
        return _dedupe(f.code for f in self.findings if f.severity is FindingSeverity.REVIEW)

    @property
    def notice_kinds(self) -> tuple[AssessmentKind, ...]:
        """Kinds that need platform copy when the clip is served."""
        found = [f.kind for f in self.findings if f.severity is FindingSeverity.NOTICE]
        return tuple(dict.fromkeys(found))

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return _dedupe(f.code for f in self.findings)

    def has_kind(self, kind: AssessmentKind) -> bool:
        return any(f.kind is kind for f in self.findings)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "degraded": self.degraded,
            "severity": self.severity.value if self.severity else None,
            "reason_codes": list(self.reason_codes),
            "notice_kinds": [k.value for k in self.notice_kinds],
        }


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------


class CoverageVerdict(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    CONFLICTED = "conflicted"
    INSUFFICIENT = "insufficient"


class FacetCoverageState(StrEnum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    ABSENT = "absent"


@dataclass(frozen=True, slots=True)
class FacetCoverage:
    """Coverage of one planned facet.

    ``required`` is the only thing that turns an absent facet into an abstain.
    A compound question asks for several facets, but only the facets whose
    absence would make the answer misleading are required (see
    :func:`required_facets_for`).
    """

    facet: str
    state: FacetCoverageState
    required: bool = False


# Facets whose absence makes a served answer misleading rather than partial.
# These are the "how/what is" style facets that a user can verify directly.
_REQUIRED_WHEN_PLANNED: frozenset[str] = frozenset(
    {
        "definition",
        "distinction",
        "cause",
        "practice",
    }
)


def required_facets_for(planned: Sequence[str]) -> tuple[str, ...]:
    """Facets that must be covered for a direct answer.

    A plan with no verifiable facet requirement (e.g. a general question)
    requires nothing, so the selector's own verdict stays authoritative.
    """
    return tuple(f for f in planned if f in _REQUIRED_WHEN_PLANNED)


@dataclass(frozen=True, slots=True)
class CoverageDecision:
    """Set-level coverage verdict for one query.

    The record is built either from the editorial set selector (which knows
    per-facet coverage) or from the served text itself, so both the terminal
    harness path and the legacy path produce the same type.

    ``authoritative`` is True when derived from a structured editorial set
    selector evaluation; it is False when inferred via heuristic text matching.
    """

    verdict: CoverageVerdict
    facets: tuple[FacetCoverage, ...] = ()
    reasons: tuple[str, ...] = ()
    authoritative: bool = False
    contract_version: str = DECISION_CONTRACT_VERSION

    @property
    def missing_required(self) -> tuple[str, ...]:
        return tuple(
            f.facet for f in self.facets if f.required and f.state is FacetCoverageState.ABSENT
        )

    @property
    def allow_direct(self) -> bool:
        return self.verdict is CoverageVerdict.SUPPORTED and not self.missing_required

    @property
    def allow_related(self) -> bool:
        """A partial set may be served as related unless an authoritative required facet is missing."""
        if self.verdict is CoverageVerdict.INSUFFICIENT:
            return False
        if self.verdict is CoverageVerdict.CONFLICTED:
            return False
        if self.authoritative and self.missing_required:
            return False
        return True

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "verdict": self.verdict.value,
            "authoritative": self.authoritative,
            "facets": [
                {"facet": f.facet, "state": f.state.value, "required": f.required}
                for f in self.facets
            ],
            "missing_required": list(self.missing_required),
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_editorial_set(cls, record: Mapping[str, object] | None) -> CoverageDecision | None:
        """Adapt the pipeline's ``editorial_set`` record to the contract.

        Returns None when the record is absent (the editorial selector did not
        run) so callers can fall back to text-derived coverage instead of
        inventing a verdict.
        """
        if not isinstance(record, Mapping):
            return None
        raw_status = str(record.get("status") or "")
        try:
            verdict = CoverageVerdict(raw_status)
        except ValueError:
            return None
        planned = [str(f) for f in (record.get("candidate_facets") or []) if isinstance(f, str)]
        raw_coverage = record.get("facet_coverage")
        coverage_map = raw_coverage if isinstance(raw_coverage, Mapping) else {}
        required = set(required_facets_for(planned))
        facets: list[FacetCoverage] = []
        for facet in planned:
            raw_state = str(coverage_map.get(facet, "absent"))
            try:
                state = FacetCoverageState(raw_state)
            except ValueError:
                state = FacetCoverageState.ABSENT
            facets.append(FacetCoverage(facet=facet, state=state, required=facet in required))
        reasons = tuple(str(r) for r in (record.get("reasons") or []) if isinstance(r, str))
        return cls(verdict=verdict, facets=tuple(facets), reasons=reasons, authoritative=True)


# ---------------------------------------------------------------------------
# Serve posture
# ---------------------------------------------------------------------------


class ServePosture(StrEnum):
    DIRECT = "direct"
    RELATED = "related"
    ABSTAIN = "abstain"


@dataclass(frozen=True, slots=True)
class ServeDecision:
    """Final serving posture for one candidate answer."""

    posture: ServePosture
    reason: str
    coverage: CoverageDecision | None = None
    assessment: ContentAssessment | None = None
    contract_version: str = DECISION_CONTRACT_VERSION

    @property
    def serves(self) -> bool:
        return self.posture is not ServePosture.ABSTAIN

    @property
    def is_direct(self) -> bool:
        return self.posture is ServePosture.DIRECT

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "posture": self.posture.value,
            "reason": self.reason,
            "coverage": self.coverage.to_dict() if self.coverage else None,
            "assessment": self.assessment.to_dict() if self.assessment else None,
        }


def resolve_serve_posture(
    *,
    pipeline_status: str,
    is_direct_answer: bool,
    coverage: CoverageDecision | None,
    assessment: ContentAssessment | None,
    primary_mode: bool,
    serve_weak_match: bool,
) -> ServeDecision:
    """Derive the serving posture from the two decision records.

    Precedence is fixed and total:

    1. an excluding content finding always abstains;
    2. a pipeline direct answer is direct only when coverage permits it;
    3. a weak match may be served as related only when the posture flags allow
       it *and* coverage permits related serving;
    4. everything else abstains.

    Replaces the former ``status == "weak_match" and ... and not is_compound``
    boolean: question *shape* no longer decides, coverage evidence does.
    """
    if assessment is not None and not assessment.may_serve:
        return ServeDecision(
            posture=ServePosture.ABSTAIN,
            reason=(
                assessment.exclusion_codes[0] if assessment.exclusion_codes else "content_excluded"
            ),
            coverage=coverage,
            assessment=assessment,
        )

    if pipeline_status == "success" and is_direct_answer:
        if coverage is None or coverage.allow_direct:
            return ServeDecision(
                posture=ServePosture.DIRECT,
                reason="direct",
                coverage=coverage,
                assessment=assessment,
            )
        # The pipeline called it direct but the set does not cover a required
        # facet: the honest posture is related, not direct.
        if coverage.allow_related:
            return ServeDecision(
                posture=ServePosture.RELATED,
                reason="partial_coverage",
                coverage=coverage,
                assessment=assessment,
            )
        return ServeDecision(
            posture=ServePosture.ABSTAIN,
            reason="required_facet_missing",
            coverage=coverage,
            assessment=assessment,
        )

    if pipeline_status == "weak_match" and primary_mode and serve_weak_match:
        if coverage is None or coverage.allow_related:
            return ServeDecision(
                posture=ServePosture.RELATED,
                reason="weak_match_related",
                coverage=coverage,
                assessment=assessment,
            )
        return ServeDecision(
            posture=ServePosture.ABSTAIN,
            reason=(
                "required_facet_missing"
                if coverage.missing_required
                else f"coverage_{coverage.verdict.value}"
            ),
            coverage=coverage,
            assessment=assessment,
        )

    return ServeDecision(
        posture=ServePosture.ABSTAIN,
        reason=f"pipeline_{pipeline_status or 'unknown'}",
        coverage=coverage,
        assessment=assessment,
    )


if __name__ == "__main__":
    _clean = ContentAssessment()
    _framing = ContentAssessment(
        findings=(
            ContentFinding(
                code="ayurvedic_framing",
                kind=AssessmentKind.WELLBEING_FRAMING,
                severity=FindingSeverity.NOTICE,
                detector="wellbeing_framing_detector",
            ),
        )
    )
    _clinical = ContentAssessment(
        findings=(
            ContentFinding(
                code="health_claim",
                kind=AssessmentKind.CLINICAL_CLAIM,
                severity=FindingSeverity.EXCLUDE,
                detector="clinical_claim_detector",
            ),
        )
    )
    assert _clean.may_serve and not _clean.requires_review
    assert _framing.may_serve and _framing.notice_kinds
    assert not _clinical.may_serve and _clinical.exclusion_codes == ("health_claim",)

    _none = CoverageDecision(verdict=CoverageVerdict.SUPPORTED)
    _missing = CoverageDecision(
        verdict=CoverageVerdict.PARTIAL,
        facets=(FacetCoverage(facet="definition", state=FacetCoverageState.ABSENT, required=True),),
    )
    _d = resolve_serve_posture(
        pipeline_status="success",
        is_direct_answer=True,
        coverage=_none,
        assessment=_clean,
        primary_mode=True,
        serve_weak_match=True,
    )
    assert _d.posture is ServePosture.DIRECT
    _r = resolve_serve_posture(
        pipeline_status="weak_match",
        is_direct_answer=False,
        coverage=_missing,
        assessment=_framing,
        primary_mode=True,
        serve_weak_match=True,
    )
    assert _r.posture is ServePosture.ABSTAIN and _r.reason == "required_facet_missing"
    _x = resolve_serve_posture(
        pipeline_status="success",
        is_direct_answer=True,
        coverage=_none,
        assessment=_clinical,
        primary_mode=True,
        serve_weak_match=True,
    )
    assert _x.posture is ServePosture.ABSTAIN and _x.reason == "health_claim"
    print("first_person_decision self-check passed")
