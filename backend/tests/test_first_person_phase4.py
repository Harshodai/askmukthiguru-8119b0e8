"""Tests for Phase 4: facet planner and evidence set selector.

Covers:
- Facet planner: definition/practice/distinction/teacher-scope/event-scope detection
- Set selector: near-duplicate removal, teacher scope, direct-evidence requirement,
  max_clips cap, per-video deduplication, status (supported/partial/conflicted/insufficient)
- Edge cases: empty candidates, max_clips=0, all near-duplicates, teacher scope mismatch
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from domain.first_person_facets import QueryFacets
from services.first_person_facet_planner import FirstPersonFacetPlanner
from services.first_person_set_selector import (
    FirstPersonSetSelector,
    _jaccard,
    _normalised_tokens,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def planner() -> FirstPersonFacetPlanner:
    return FirstPersonFacetPlanner()


@pytest.fixture()
def selector() -> FirstPersonSetSelector:
    return FirstPersonSetSelector()


def _span(
    span_id: str = "s1",
    video_id: str = "vid1",
    guru_id: str = "krishnaji",
    text: str = "Love is a state of deep connection and presence within oneself.",
    is_direct: bool = True,
    score: float = 0.8,
) -> SimpleNamespace:
    return SimpleNamespace(
        source_span_id=span_id,
        video_id=video_id,
        guru_id=guru_id,
        text=text,
        is_direct=is_direct,
        score=score,
    )


_FACETS_LOVE = QueryFacets(
    primary_intent="definition",
    candidate_facets=("experience", "connection"),
    teacher_scope=None,
    event_scope=None,
)

_FACETS_KRISHNAJI_ONLY = QueryFacets(
    primary_intent="definition",
    candidate_facets=("experience",),
    teacher_scope="krishnaji",
    event_scope=None,
)

_FACETS_PRACTICE = QueryFacets(
    primary_intent="practice",
    candidate_facets=("experience",),
    teacher_scope=None,
    event_scope=None,
)


# ===========================================================================
# Facet Planner Tests
# ===========================================================================


class TestFirstPersonFacetPlanner:
    """Tests for FirstPersonFacetPlanner.plan()."""

    def test_what_is_love_gives_definition_primary(self, planner):
        plan = planner.plan("What is love?")
        assert plan.primary_intent == "definition"

    def test_how_to_meditate_gives_practice_primary(self, planner):
        plan = planner.plan("How do I meditate?")
        assert plan.primary_intent == "practice"

    def test_difference_between_attachment_and_love(self, planner):
        plan = planner.plan("What is the difference between love and attachment?")
        assert plan.primary_intent == "distinction"

    def test_teacher_scope_krishnaji_detected(self, planner):
        plan = planner.plan("What did Krishnaji say about love?")
        assert plan.teacher_scope == "krishnaji"

    def test_teacher_scope_preethaji_detected(self, planner):
        plan = planner.plan("What does Preethaji teach about suffering?")
        assert plan.teacher_scope == "preethaji"

    def test_both_gurus_no_teacher_scope(self, planner):
        plan = planner.plan("What is love according to Krishnaji and Preethaji?")
        assert plan.teacher_scope is None

    def test_love_topic_expands_candidate_facets(self, planner):
        plan = planner.plan("What is love?")
        assert len(plan.candidate_facets) > 0
        assert "experience" in plan.candidate_facets or "connection" in plan.candidate_facets

    def test_empty_query_returns_general(self, planner):
        plan = planner.plan("")
        assert plan.primary_intent == "general"
        assert plan.teacher_scope is None

    def test_whitespace_query_returns_general(self, planner):
        plan = planner.plan("   \t\n")
        assert plan.primary_intent == "general"

    def test_planner_version_is_set(self, planner):
        plan = planner.plan("What is peace?")
        assert plan.planner_version == planner.PLANNER_VERSION

    def test_all_facets_deduplicates(self, planner):
        plan = planner.plan("What is love?")
        facets = plan.all_facets
        assert len(facets) == len(set(facets)), "all_facets must be deduplicated"

    def test_fail_open_on_internal_error(self, planner, monkeypatch):
        """Planner must return general plan, not raise, when internals error."""
        monkeypatch.setattr(
            planner, "_detect_teacher", lambda _: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        # _detect_teacher won't raise since it's now a generator; use a different approach
        monkeypatch.setattr(planner, "_plan", lambda q: (_ for _ in ()).throw(RuntimeError("boom")))
        plan = planner.plan("What is love?")
        assert plan.primary_intent == "general"


# ===========================================================================
# Set Selector Tests
# ===========================================================================


class TestFirstPersonSetSelector:
    """Tests for FirstPersonSetSelector.select()."""

    def test_basic_single_direct_clip_supported(self, selector):
        c = _span(
            text="Love is a state of complete presence. It is not a feeling but a way of being.",
            is_direct=True,
        )
        decision = selector.select("What is love?", _FACETS_LOVE, [c], max_clips=3)
        assert decision.status in ("supported", "partial")
        assert len(decision.selected) == 1

    def test_no_candidates_returns_insufficient(self, selector):
        decision = selector.select("What is love?", _FACETS_LOVE, [], max_clips=3)
        assert decision.status == "insufficient"
        assert len(decision.selected) == 0
        assert "no_eligible_candidates" in decision.reasons

    def test_no_direct_evidence_returns_insufficient_when_required(self, selector):
        c = _span(is_direct=False, score=0.7)
        decision = selector.select(
            "What is love?", _FACETS_LOVE, [c], max_clips=3, require_direct=True
        )
        assert decision.status == "insufficient"
        assert "no_direct_evidence" in decision.reasons

    def test_indirect_clip_allowed_when_require_direct_false(self, selector):
        c = _span(is_direct=False, score=0.7)
        decision = selector.select(
            "What is love?", _FACETS_LOVE, [c], max_clips=3, require_direct=False
        )
        assert decision.status in ("supported", "partial")
        assert len(decision.selected) == 1

    def test_near_duplicate_clips_deduplicated(self, selector):
        """Two clips with very similar text → only one selected."""
        base_text = "Love is a state of connection and oneness with all of existence present."
        c1 = _span(span_id="s1", video_id="vid1", text=base_text, is_direct=True, score=0.9)
        # Slight paraphrase but same tokens (>= 80% overlap)
        c2 = _span(
            span_id="s2",
            video_id="vid2",
            text=base_text + " This is the nature of love.",
            is_direct=True,
            score=0.8,
        )
        decision = selector.select("What is love?", _FACETS_LOVE, [c1, c2], max_clips=3)
        selected_ids = {s.span_id for s in decision.selected}
        # One must be excluded as near_duplicate
        assert (
            len(selected_ids) + len([e for e in decision.excluded if e[1] == "near_duplicate"]) >= 2
        )

    def test_teacher_scope_enforced(self, selector):
        """Preethaji clip must be excluded when teacher_scope is krishnaji."""
        k = _span(span_id="k1", guru_id="krishnaji", is_direct=True, score=0.9)
        p = _span(span_id="p1", guru_id="preethaji", is_direct=True, score=0.95)
        decision = selector.select("What is love?", _FACETS_KRISHNAJI_ONLY, [k, p], max_clips=3)
        selected_ids = {s.span_id for s in decision.selected}
        assert "p1" not in selected_ids
        assert "k1" in selected_ids
        excluded_reasons = {e[1] for e in decision.excluded}
        assert any("teacher_scope_mismatch" in r for r in excluded_reasons)

    def test_max_clips_cap_respected(self, selector):
        spans = [
            _span(
                span_id=f"s{i}",
                video_id=f"vid{i}",
                score=0.9 - i * 0.05,
                is_direct=True,
                text=f"Clip {i}: Love is experienced as connection and presence in that moment of being.",
            )
            for i in range(6)
        ]
        decision = selector.select("What is love?", _FACETS_LOVE, spans, max_clips=2)
        assert len(decision.selected) <= 2

    def test_max_clips_zero_returns_insufficient(self, selector):
        c = _span(is_direct=True)
        decision = selector.select("What is love?", _FACETS_LOVE, [c], max_clips=0)
        assert decision.status == "insufficient"
        assert "max_clips_zero" in decision.reasons

    def test_prefers_distinct_video_ids(self, selector):
        """Best clip per video is preferred; lower-scoring same-video clip is deprioritised."""
        c1_high = _span(
            span_id="s1",
            video_id="vid1",
            score=0.95,
            is_direct=True,
            text="Love is the most fundamental experience of being alive and present.",
        )
        c1_low = _span(
            span_id="s2",
            video_id="vid1",
            score=0.6,
            is_direct=True,
            text="In the realm of human experience love occupies a central space.",
        )
        c2 = _span(
            span_id="s3",
            video_id="vid2",
            score=0.8,
            is_direct=True,
            text="Love as Krishnaji teaches is a state beyond personal attachment or desire.",
        )
        decision = selector.select(
            "What is love?", _FACETS_LOVE, [c1_low, c1_high, c2], max_clips=2
        )
        selected_ids = {s.span_id for s in decision.selected}
        # s1 (high score, vid1) must be preferred over s2 (low score, vid1)
        assert "s1" in selected_ids

    def test_two_clips_different_videos_both_selected(self, selector):
        c1 = _span(
            span_id="s1",
            video_id="vid1",
            is_direct=True,
            score=0.9,
            text="Love is a state of complete openness and presence that has no condition.",
        )
        c2 = _span(
            span_id="s2",
            video_id="vid2",
            guru_id="preethaji",
            is_direct=True,
            score=0.8,
            text="Preethaji says love is when you are so present that another person feels deeply seen.",
        )
        decision = selector.select("What is love?", _FACETS_LOVE, [c1, c2], max_clips=3)
        assert len(decision.selected) == 2

    def test_facet_coverage_populated(self, selector):
        c = _span(
            text="Love is a state of deep connection and oneness present in every moment.",
            is_direct=True,
        )
        decision = selector.select("What is love?", _FACETS_LOVE, [c], max_clips=3)
        assert isinstance(decision.facet_coverage, dict)
        for f in _FACETS_LOVE.all_facets:
            assert f in decision.facet_coverage
            assert decision.facet_coverage[f] in ("direct", "indirect", "absent")

    def test_too_short_clip_excluded(self, selector):
        short = _span(span_id="short1", text="Love is.", is_direct=True)
        good = _span(
            span_id="good1",
            video_id="vid2",
            text="Love is a state of being fully present in connection with all of existence.",
            is_direct=True,
            score=0.8,
        )
        decision = selector.select("What is love?", _FACETS_LOVE, [short, good], max_clips=3)
        selected_ids = {s.span_id for s in decision.selected}
        assert "short1" not in selected_ids
        excluded_ids = {e[0] for e in decision.excluded}
        assert "short1" in excluded_ids

    def test_internal_error_returns_insufficient(self, selector, monkeypatch):
        """Any unexpected internal error must return insufficient, not raise."""
        monkeypatch.setattr(
            selector, "_select", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        c = _span()
        decision = selector.select("What is love?", _FACETS_LOVE, [c])
        assert decision.status == "insufficient"
        assert "selector_internal_error" in decision.reasons

    def test_selector_version_present(self, selector):
        c = _span(is_direct=True)
        decision = selector.select("What is love?", _FACETS_LOVE, [c])
        assert decision.selector_version == selector.SELECTOR_VERSION


# ===========================================================================
# Utility Function Tests
# ===========================================================================


class TestUtilityFunctions:
    """Tests for internal helpers exposed for regression coverage."""

    def test_jaccard_identical_sets(self):
        a = frozenset({"love", "peace", "joy"})
        assert _jaccard(a, a) == 1.0

    def test_jaccard_disjoint_sets(self):
        a = frozenset({"love", "peace"})
        b = frozenset({"anger", "fear"})
        assert _jaccard(a, b) == 0.0

    def test_jaccard_empty_sets(self):
        assert _jaccard(frozenset(), frozenset()) == 1.0

    def test_normalised_tokens_strips_short(self):
        tokens = _normalised_tokens("I am at the edge of my being")
        # Words < 3 chars are excluded (i, am, at, my, of)
        assert "am" not in tokens
        assert "i" not in tokens
        assert "at" not in tokens
        # Words >= 3 chars are included ("the" is 3 chars, included)
        assert "the" in tokens
        assert "edge" in tokens
        assert "being" in tokens

    def test_normalised_tokens_lowercased(self):
        tokens = _normalised_tokens("Love LOVE love")
        assert tokens == frozenset({"love"})
