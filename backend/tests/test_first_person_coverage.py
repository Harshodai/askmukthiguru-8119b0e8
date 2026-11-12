"""Coverage decides direct vs related — question shape does not.

The retired rule was "a compound question may never be served as a weak match".
That made punctuation decisive: two questions in one sentence lost the related
answer that the same sentence with one question mark received. These tests pin
the replacement: the coverage record decides, and an editorial-set record is
authoritative when present.
"""

from __future__ import annotations

from domain.first_person_decision import CoverageVerdict, FacetCoverageState
from services.first_person_coverage import coverage_for_served_text


def _by_facet(decision):
    return {facet.facet: facet for facet in decision.facets}


def test_general_intent_has_no_facet_to_miss():
    decision = coverage_for_served_text(
        "Tell me about the teaching.", "Peace is the awareness of oneness.", is_direct=True
    )
    assert decision.verdict is CoverageVerdict.SUPPORTED
    assert decision.allow_direct is True


def test_inferred_missing_required_facet_blocks_direct_but_allows_related():
    decision = coverage_for_served_text(
        "What is inner peace and how do I practice it?",
        "The mind becomes still when you are aware of the present moment.",
        is_direct=False,
    )
    assert "practice" in decision.missing_required
    assert decision.allow_direct is False
    # Inferred coverage downgrades direct -> related, never abstains
    assert decision.allow_related is True
    assert decision.authoritative is False


def test_authoritative_missing_required_facet_blocks_related():
    decision = coverage_for_served_text(
        "What is inner peace and how do I practice it?",
        "The mind becomes still when you are aware of the present moment.",
        is_direct=False,
        editorial_set={
            "status": "partial",
            "candidate_facets": ["practice"],
            "facet_coverage": {"practice": "absent"},
            "reasons": ["practice_absent"],
        },
    )
    assert "practice" in decision.missing_required
    assert decision.allow_direct is False
    assert decision.allow_related is False
    assert decision.authoritative is True


def test_present_required_facet_allows_a_related_answer():
    decision = coverage_for_served_text(
        "What is inner peace and how do I practice it?",
        "Inner peace is the practice of sitting quietly and watching the breath.",
        is_direct=False,
    )
    states = {name: facet.state for name, facet in _by_facet(decision).items()}
    assert states.get("practice") is not FacetCoverageState.ABSENT
    assert decision.allow_related is True


def test_editorial_set_record_is_authoritative():
    decision = coverage_for_served_text(
        "What is inner peace?",
        "Inner peace is stillness.",
        is_direct=True,
        editorial_set={
            "status": "conflicted",
            "candidate_facets": ["definition"],
            "facet_coverage": {"definition": "direct"},
            "reasons": ["teacher_scope_conflict"],
        },
    )
    assert decision.verdict is CoverageVerdict.CONFLICTED
    assert decision.allow_related is False


def test_absent_editorial_record_falls_back_to_the_text():
    decision = coverage_for_served_text(
        "What is inner peace?",
        "Inner peace is stillness.",
        is_direct=True,
        editorial_set=None,
    )
    assert decision.verdict in {CoverageVerdict.SUPPORTED, CoverageVerdict.PARTIAL}


def test_planner_failure_never_blocks_serving():
    """The planner is fail-open by contract; coverage must not invent a miss."""
    import services.first_person_facet_planner as planner_module
    from services.first_person_coverage import coverage_for_served_text as cov

    class _Boom:
        def plan(self, _query):  # noqa: D401 - test double
            raise RuntimeError("planner exploded")

    original = planner_module.get_default_planner
    planner_module.get_default_planner = lambda: _Boom()
    try:
        decision = cov("What is inner peace?", "Inner peace is stillness.", is_direct=True)
    finally:
        planner_module.get_default_planner = original
    assert decision.verdict is CoverageVerdict.SUPPORTED
    assert decision.reasons == ("planner_unavailable",)


def test_empty_served_text_cannot_cover_a_required_facet():
    decision = coverage_for_served_text(
        "What is inner peace?",
        "",
        is_direct=False,
    )
    assert decision.allow_related is False


def test_semantic_facet_coverage_bypasses_keyword_counter():
    # Text describes meditation instructions without literal keywords: "method", "technique", "practice"
    text = "Sit quietly, bring your attention to the rhythm of breathing, and watch thoughts rise and fall."
    # Without semantic facets, keyword counter scores 0 on practice
    decision_keyword = coverage_for_served_text(
        "How do I practice awareness?",
        text,
        is_direct=True,
    )
    assert "practice" in decision_keyword.missing_required

    # With semantic facets provided from judge evaluation, practice facet is authoritatively covered
    decision_semantic = coverage_for_served_text(
        "How do I practice awareness?",
        text,
        is_direct=True,
        semantic_facets=["practice"],
    )
    assert "practice" not in decision_semantic.missing_required
    assert decision_semantic.verdict is CoverageVerdict.SUPPORTED
    assert decision_semantic.allow_direct is True
    assert decision_semantic.authoritative is True


def test_editorial_set_covered_facets_authoritative():
    text = "Sit quietly and observe the stillness within."
    editorial_set = {
        "status": "supported",
        "covered_facets": ["practice", "definition"],
        "content_safety": "clean",
    }
    decision = coverage_for_served_text(
        "How do I practice stillness and what is it?",
        text,
        is_direct=True,
        editorial_set=editorial_set,
    )
    assert decision.verdict is CoverageVerdict.SUPPORTED
    assert decision.allow_direct is True
    assert decision.authoritative is True
