"""The typed decision contract: content assessment, coverage, serve posture.

The point of the contract is that a decision is computed once and then *read*.
These tests pin the three properties that make that safe:

* the severity lattice is total (an EXCLUDE finding always wins);
* coverage, not question shape, decides direct vs related vs abstain;
* a required-but-absent facet downgrades an over-confident "direct" verdict.
"""

from __future__ import annotations

import pytest

from domain.first_person_decision import (
    DECISION_CONTRACT_VERSION,
    AssessmentKind,
    ContentAssessment,
    ContentFinding,
    CoverageDecision,
    CoverageVerdict,
    FacetCoverage,
    FacetCoverageState,
    FindingSeverity,
    ServePosture,
    required_facets_for,
    resolve_serve_posture,
)


def _finding(
    kind: AssessmentKind,
    severity: FindingSeverity,
    code: str = "code",
) -> ContentFinding:
    return ContentFinding(code=code, kind=kind, severity=severity, detector="test_detector")


def _assessment(*findings: ContentFinding, degraded: bool = False) -> ContentAssessment:
    return ContentAssessment(findings=tuple(findings), degraded=degraded)


def _decision(
    *,
    status: str,
    direct: bool,
    coverage: CoverageDecision | None = None,
    assessment: ContentAssessment | None = None,
    primary_mode: bool = True,
    serve_weak_match: bool = True,
):
    return resolve_serve_posture(
        pipeline_status=status,
        is_direct_answer=direct,
        coverage=coverage,
        assessment=assessment,
        primary_mode=primary_mode,
        serve_weak_match=serve_weak_match,
    )


# ---------------------------------------------------------------------------
# Content assessment
# ---------------------------------------------------------------------------


def test_clean_assessment_serves_and_reports_no_severity():
    clean = _assessment()
    assert clean.may_serve is True
    assert clean.severity is None
    assert clean.reason_codes == ()
    assert clean.exclusion_codes == ()


def test_exclude_finding_wins_over_lower_severities():
    combined = _assessment(
        _finding(AssessmentKind.WELLBEING_FRAMING, FindingSeverity.NOTICE, "framing"),
        _finding(AssessmentKind.CLINICAL_CLAIM, FindingSeverity.EXCLUDE, "health_claim"),
        _finding(AssessmentKind.EVENT_BOUND, FindingSeverity.REVIEW, "event_bound"),
    )
    assert combined.may_serve is False
    assert combined.severity is FindingSeverity.EXCLUDE
    assert combined.exclusion_codes == ("health_claim",)
    assert combined.notice_kinds == (AssessmentKind.WELLBEING_FRAMING,)


def test_degraded_assessment_fails_closed():
    degraded = _assessment(degraded=True)
    assert degraded.may_serve is False
    assert degraded.severity is FindingSeverity.EXCLUDE


def test_reason_codes_are_deduped_in_order():
    dup = _assessment(
        _finding(AssessmentKind.CLINICAL_CLAIM, FindingSeverity.EXCLUDE, "health_claim"),
        _finding(AssessmentKind.CAUSAL_ETIOLOGY, FindingSeverity.EXCLUDE, "health_claim"),
        _finding(AssessmentKind.EVENT_BOUND, FindingSeverity.REVIEW, "event_bound"),
    )
    assert dup.reason_codes == ("health_claim", "event_bound")


def test_assessment_dict_is_json_shaped():
    payload = _assessment(
        _finding(AssessmentKind.WELLBEING_FRAMING, FindingSeverity.NOTICE, "framing")
    ).to_dict()
    assert payload["contract_version"] == DECISION_CONTRACT_VERSION
    assert payload["severity"] == "notice"
    assert payload["notice_kinds"] == ["wellbeing_framing"]


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------


def test_required_facets_are_a_bounded_subset():
    assert required_facets_for(["definition", "practice", "experience"]) == (
        "definition",
        "practice",
    )
    assert required_facets_for(["general"]) == ()


def test_supported_coverage_allows_direct_and_related():
    decision = CoverageDecision(verdict=CoverageVerdict.SUPPORTED)
    assert decision.allow_direct is True
    assert decision.allow_related is True
    assert decision.missing_required == ()


def test_authoritative_partial_coverage_with_missing_required_allows_neither():
    decision = CoverageDecision(
        verdict=CoverageVerdict.PARTIAL,
        facets=(
            FacetCoverage(
                facet="definition",
                state=FacetCoverageState.ABSENT,
                required=True,
            ),
        ),
        authoritative=True,
    )
    assert decision.missing_required == ("definition",)
    assert decision.allow_direct is False
    assert decision.allow_related is False


def test_inferred_partial_coverage_with_missing_required_allows_related():
    decision = CoverageDecision(
        verdict=CoverageVerdict.PARTIAL,
        facets=(
            FacetCoverage(
                facet="definition",
                state=FacetCoverageState.ABSENT,
                required=True,
            ),
        ),
        authoritative=False,
    )
    assert decision.missing_required == ("definition",)
    assert decision.allow_direct is False
    assert decision.allow_related is True


def test_partial_coverage_of_optional_facets_still_allows_related():
    decision = CoverageDecision(
        verdict=CoverageVerdict.PARTIAL,
        facets=(
            FacetCoverage(
                facet="experience",
                state=FacetCoverageState.ABSENT,
                required=False,
            ),
        ),
    )
    assert decision.allow_direct is False
    assert decision.allow_related is True


@pytest.mark.parametrize("verdict", [CoverageVerdict.INSUFFICIENT, CoverageVerdict.CONFLICTED])
def test_insufficient_and_conflicted_never_serve_as_related(verdict):
    decision = CoverageDecision(verdict=verdict)
    assert decision.allow_related is False


def test_from_editorial_set_adapts_the_pipeline_record():
    decision = CoverageDecision.from_editorial_set(
        {
            "status": "partial",
            "candidate_facets": ["definition", "practice"],
            "facet_coverage": {"definition": "direct"},
            "reasons": ["practice_absent"],
        }
    )
    assert decision is not None
    assert decision.verdict is CoverageVerdict.PARTIAL
    by_facet = {f.facet: f for f in decision.facets}
    assert by_facet["definition"].state is FacetCoverageState.DIRECT
    assert by_facet["practice"].state is FacetCoverageState.ABSENT
    assert by_facet["practice"].required is True
    assert decision.missing_required == ("practice",)
    assert decision.reasons == ("practice_absent",)


@pytest.mark.parametrize(
    "record",
    [
        None,
        {},
        {"status": "not_a_verdict"},
        {"status": "supported", "candidate_facets": None},
    ],
)
def test_from_editorial_set_never_invents_a_verdict(record):
    decision = CoverageDecision.from_editorial_set(record)
    if record is None or record.get("status") not in {"supported", "partial", "conflicted", "insufficient"}:
        assert decision is None
    else:
        assert decision is not None


# ---------------------------------------------------------------------------
# Serve posture
# ---------------------------------------------------------------------------


def test_direct_answer_is_direct_when_coverage_permits():
    decision = _decision(
        status="success",
        direct=True,
        coverage=CoverageDecision(verdict=CoverageVerdict.SUPPORTED),
        assessment=_assessment(),
    )
    assert decision.posture is ServePosture.DIRECT
    assert decision.reason == "direct"
    assert decision.serves is True


def test_excluding_content_abstains_even_for_a_direct_answer():
    decision = _decision(
        status="success",
        direct=True,
        coverage=CoverageDecision(verdict=CoverageVerdict.SUPPORTED),
        assessment=_assessment(
            _finding(AssessmentKind.CLINICAL_CLAIM, FindingSeverity.EXCLUDE, "health_claim")
        ),
    )
    assert decision.posture is ServePosture.ABSTAIN
    assert decision.reason == "health_claim"


def test_direct_answer_with_missing_required_facet_becomes_related():
    decision = _decision(
        status="success",
        direct=True,
        coverage=CoverageDecision(
            verdict=CoverageVerdict.PARTIAL,
            facets=(
                FacetCoverage(
                    facet="practice",
                    state=FacetCoverageState.ABSENT,
                    required=False,
                ),
            ),
        ),
        assessment=_assessment(),
    )
    assert decision.posture is ServePosture.RELATED
    assert decision.reason == "partial_coverage"


def test_direct_answer_with_inferred_missing_required_facet_downgrades_to_related():
    decision = _decision(
        status="success",
        direct=True,
        coverage=CoverageDecision(
            verdict=CoverageVerdict.PARTIAL,
            facets=(
                FacetCoverage(
                    facet="practice",
                    state=FacetCoverageState.ABSENT,
                    required=True,
                ),
            ),
            authoritative=False,
        ),
        assessment=_assessment(),
    )
    assert decision.posture is ServePosture.RELATED
    assert decision.reason == "partial_coverage"


def test_direct_answer_with_authoritative_missing_required_facet_abstains():
    decision = _decision(
        status="success",
        direct=True,
        coverage=CoverageDecision(
            verdict=CoverageVerdict.PARTIAL,
            facets=(
                FacetCoverage(
                    facet="practice",
                    state=FacetCoverageState.ABSENT,
                    required=True,
                ),
            ),
            authoritative=True,
        ),
        assessment=_assessment(),
    )
    assert decision.posture is ServePosture.ABSTAIN
    assert decision.reason == "required_facet_missing"


def test_weak_match_is_related_when_coverage_permits():
    decision = _decision(
        status="weak_match",
        direct=False,
        coverage=CoverageDecision(verdict=CoverageVerdict.PARTIAL),
        assessment=_assessment(),
    )
    assert decision.posture is ServePosture.RELATED
    assert decision.reason == "weak_match_related"


def test_compound_question_shape_no_longer_decides():
    """The retired rule was ``weak_match and not is_compound``.

    A compound question whose facets are covered must serve as related; shape is
    not part of the decision any more (only the coverage record is).
    """
    decision = _decision(
        status="weak_match",
        direct=False,
        coverage=CoverageDecision(verdict=CoverageVerdict.SUPPORTED),
        assessment=_assessment(),
    )
    assert decision.posture is ServePosture.RELATED


@pytest.mark.parametrize("primary,weak", [(False, True), (True, False), (False, False)])
def test_weak_match_posture_flags_are_respected(primary, weak):
    decision = _decision(
        status="weak_match",
        direct=False,
        coverage=CoverageDecision(verdict=CoverageVerdict.SUPPORTED),
        assessment=_assessment(),
        primary_mode=primary,
        serve_weak_match=weak,
    )
    assert decision.posture is ServePosture.ABSTAIN
    assert decision.reason == "pipeline_weak_match"


def test_abstained_pipeline_never_serves():
    decision = _decision(status="abstained", direct=False, assessment=_assessment())
    assert decision.posture is ServePosture.ABSTAIN
    assert decision.reason == "pipeline_abstained"


def test_serve_decision_dict_is_json_shaped():
    payload = _decision(
        status="weak_match",
        direct=False,
        coverage=CoverageDecision(verdict=CoverageVerdict.PARTIAL),
        assessment=_assessment(),
    ).to_dict()
    assert payload["posture"] == "related"
    assert payload["coverage"]["verdict"] == "partial"
    assert payload["assessment"]["severity"] is None
