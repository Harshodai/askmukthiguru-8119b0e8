"""Coverage decision shared by the terminal harness path and the legacy path.

The question "did the evidence answer what was asked" used to be answered by
question *shape*: a compound question was never allowed to be served as a weak
match, no matter what the clips actually covered. That made the rule depend on
punctuation rather than evidence.

This module turns the deterministic facet plan plus the served text (or the
editorial selector's own record) into one typed
:class:`~domain.first_person_decision.CoverageDecision`. Callers read
``allow_direct`` / ``allow_related``; nobody re-derives the rule.

No LLM calls, no I/O, no corpus reads; deterministic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from domain.first_person_decision import (
    CoverageDecision,
    CoverageVerdict,
    FacetCoverage,
    FacetCoverageState,
    required_facets_for,
)

COVERAGE_VERSION = "first_person_coverage_v1"

# A facet is considered present when the served text carries at least this much
# of the facet's own vocabulary. Deliberately conservative: absence of the
# keyword does not prove absence of the idea, so an uncovered required facet
# makes the answer *related*, and only a genuinely uncovered plan abstains.
DIRECT_FACET_SCORE = 0.5
PRESENT_FACET_SCORE = 0.15


def coverage_for_served_text(
    query: str,
    text: str,
    *,
    is_direct: bool,
    editorial_set: Mapping[str, object] | None = None,
    semantic_facets: Sequence[str] | None = None,
) -> CoverageDecision:
    """Coverage verdict for one already-gated answer.

    When the editorial selector or semantic judge ran, its record is authoritative
    (it knows the per-facet assignment). When semantic facet coverage is present,
    it authoritatively determines facet presence, bypassing brittle keyword-counter
    matching. Otherwise the deterministic planner supplies the facets and the served
    text is matched against the keyword scorer as an offline/unconfigured fallback.
    """
    if isinstance(editorial_set, Mapping):
        cov_facets = editorial_set.get("covered_facets")
        if cov_facets and isinstance(cov_facets, (list, tuple, set)):
            cov_facets_list = [str(f) for f in cov_facets if isinstance(f, str)]
            if not editorial_set.get("candidate_facets") or not editorial_set.get("facet_coverage"):
                norm_editorial = dict(editorial_set)
                is_supp = str(editorial_set.get("status") or "") == "supported"
                norm_editorial.setdefault(
                    "candidate_facets", list(dict.fromkeys(["general"] + cov_facets_list))
                )
                norm_editorial.setdefault(
                    "facet_coverage",
                    {f: "direct" if is_supp else "indirect" for f in norm_editorial["candidate_facets"]},
                )
                editorial_set = norm_editorial

    authoritative = CoverageDecision.from_editorial_set(editorial_set)
    if authoritative is not None:
        return authoritative

    from services.first_person_facet_planner import get_default_planner

    try:
        plan = get_default_planner().plan(query)
    except Exception:  # noqa: BLE001 - planner is fail-open by contract
        return CoverageDecision(
            verdict=CoverageVerdict.SUPPORTED,
            reasons=("planner_unavailable",),
            authoritative=False,
        )

    planned: Sequence[str] = plan.all_facets or ("general",)
    if tuple(planned) == ("general",):
        # A general question has no facet to be missing; the pipeline's own
        # relevance gate owns the decision.
        return CoverageDecision(
            verdict=CoverageVerdict.SUPPORTED,
            reasons=("general_intent",),
            authoritative=False,
        )

    from domain.first_person_facets import _FACET_KEYWORD_MAP
    from services.first_person_facet_planner import _FACET_PATTERN
    from services.first_person_set_selector import _score_facet_match

    # Only facets explicitly queried (in primary intent or matched in query keywords)
    # can be required. Candidate facets from topic broadening are optional retrieval hints.
    explicit_facets = {
        _FACET_KEYWORD_MAP[hit.group(1).lower()]
        for hit in _FACET_PATTERN.finditer(query.lower())
        if hit.group(1).lower() in _FACET_KEYWORD_MAP
    }
    if plan.primary_intent and plan.primary_intent != "general":
        explicit_facets.add(plan.primary_intent)

    # Extract semantic facets from editorial_set if not explicitly passed
    if semantic_facets is None and isinstance(editorial_set, Mapping):
        ef = editorial_set.get("covered_facets")
        if isinstance(ef, (list, tuple, set)):
            semantic_facets = [str(x) for x in ef if isinstance(x, str)]

    semantic_set = (
        {str(f).strip().lower() for f in semantic_facets} if semantic_facets else set()
    )

    required = set(required_facets_for(tuple(explicit_facets)))
    facets: list[FacetCoverage] = []
    used_semantic = False
    for facet in planned:
        if semantic_set and facet.lower() in semantic_set:
            state = FacetCoverageState.DIRECT if is_direct else FacetCoverageState.INDIRECT
            used_semantic = True
        else:
            score = _score_facet_match(text, facet, semantic_facets=semantic_facets)
            if not text.strip():
                state = FacetCoverageState.ABSENT
            elif score >= 0.3 and is_direct:
                state = FacetCoverageState.DIRECT
            elif score >= PRESENT_FACET_SCORE:
                state = FacetCoverageState.INDIRECT
            else:
                state = FacetCoverageState.ABSENT
        facets.append(FacetCoverage(facet=facet, state=state, required=facet in required))

    covered = [f for f in facets if f.state is not FacetCoverageState.ABSENT]
    if not covered:
        if not text.strip():
            verdict = CoverageVerdict.INSUFFICIENT
        else:
            verdict = CoverageVerdict.PARTIAL
    elif len(covered) == len(facets):
        verdict = CoverageVerdict.SUPPORTED
    elif required and all(f.state is not FacetCoverageState.ABSENT for f in facets if f.required):
        # All required facets are covered; missing optional candidate facets do not block supported verdict
        verdict = CoverageVerdict.SUPPORTED
    elif not required and covered:
        verdict = CoverageVerdict.SUPPORTED
    else:
        verdict = CoverageVerdict.PARTIAL

    reasons_list = [
        f"{f.facet}_absent" for f in facets if f.state is FacetCoverageState.ABSENT
    ]
    if used_semantic:
        reasons_list.append("semantic_facet_coverage")
    reasons = tuple(reasons_list)
    return CoverageDecision(
        verdict=verdict,
        facets=tuple(facets),
        reasons=reasons,
        authoritative=used_semantic,
    )


if __name__ == "__main__":
    _general = coverage_for_served_text(
        "Tell me about the teaching.", "Peace is the awareness of oneness.", is_direct=True
    )
    assert _general.verdict is CoverageVerdict.SUPPORTED

    _defn = coverage_for_served_text(
        "What is inner peace and how do I practice it?",
        "Inner peace is the natural state when the mind is still. "
        "The practice is to sit and observe the breath.",
        is_direct=True,
    )
    # Both required facets (definition and practice) are directly covered;
    # missing optional candidate facets do not prevent a supported direct verdict.
    assert _defn.verdict is CoverageVerdict.SUPPORTED
    assert _defn.allow_direct and _defn.allow_related

    _missing = coverage_for_served_text(
        "What is inner peace and how do I practice it?",
        "The mind becomes still when you are aware of the present moment.",
        is_direct=False,
    )
    assert "practice" in _missing.missing_required
    assert not _missing.allow_direct
    # Inferred coverage with missing required facet allows related serving (downgrades, never abstains)
    assert _missing.allow_related is True

    _authoritative = coverage_for_served_text(
        "What is inner peace?",
        "Inner peace is stillness.",
        is_direct=True,
        editorial_set={
            "status": "partial",
            "candidate_facets": ["definition"],
            "facet_coverage": {"definition": "indirect"},
            "reasons": ["indirect_only"],
        },
    )
    assert _authoritative.verdict is CoverageVerdict.PARTIAL
    assert _authoritative.authoritative is True
    print("first_person_coverage self-check passed")
