"""Deterministic facet planner for first-person query decomposition.

Maps a user query to a ``QueryFacets`` plan without any LLM call.
The plan is a set of retrieval hypotheses — the selector is responsible for
reporting absent facets honestly rather than force-filling them.

Design constraints:
- No LLM calls, no network calls, no Qdrant reads.
- Deterministic: same query → same plan.
- Fail-open: any exception returns a general-intent plan.
- Does not alter the query text or filter corpus eligibility.
"""

from __future__ import annotations

import re

from domain.first_person_facets import (
    _FACET_KEYWORD_MAP,
    _TEACHER_NAME_MAP,
    FACET_PLANNER_VERSION,
    QueryFacets,
)

# ---------------------------------------------------------------------------
# Pre-compiled patterns (built once at import time).
# ---------------------------------------------------------------------------

# Match teacher names (case-insensitive word boundary).
_TEACHER_PATTERN = re.compile(
    r"\b("
    + "|".join(re.escape(k) for k in sorted(_TEACHER_NAME_MAP, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)

# Match facet-keyword phrases. Longer phrases first to avoid partial shadowing.
_sorted_kws = sorted(_FACET_KEYWORD_MAP.keys(), key=len, reverse=True)
_FACET_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _sorted_kws) + r")\b",
    re.IGNORECASE,
)

# General topic words that broaden the candidate facets.
_TOPIC_BROAD_MAP: dict[str, tuple[str, ...]] = {
    "love": ("definition", "experience", "connection", "attachment", "relationship"),
    "happiness": ("definition", "experience", "inner_state"),
    "suffering": ("definition", "cause", "transformation", "experience"),
    "meditation": ("practice", "experience", "inner_state"),
    "consciousness": ("definition", "awareness", "experience"),
    "peace": ("definition", "inner_state", "experience"),
    "anger": ("cause", "transformation", "experience"),
    "fear": ("cause", "transformation", "experience"),
    "grief": ("experience", "cause", "transformation"),
    "joy": ("definition", "experience", "inner_state"),
    "compassion": ("definition", "experience", "practice", "compassion"),
    "attachment": ("definition", "cause", "suffering", "attachment"),
    "liberation": ("definition", "transformation", "experience"),
    "awareness": ("definition", "experience", "awareness", "presence"),
}
_BROAD_TOPIC_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _TOPIC_BROAD_MAP) + r")\b",
    re.IGNORECASE,
)


class FirstPersonFacetPlanner:
    """Map a user query string to a ``QueryFacets`` plan.

    The returned plan is a set of retrieval hypotheses. The selector uses it
    to organize candidates and report coverage; it must never force a clip into
    a facet slot just to appear complete.
    """

    PLANNER_VERSION = FACET_PLANNER_VERSION

    def plan(self, query: str) -> QueryFacets:
        """Return a ``QueryFacets`` for ``query``.

        Fail-open: returns a general-intent plan on empty query or exception.
        """
        try:
            return self._plan(query)
        except Exception:  # noqa: BLE001 — fail-open; never raises
            return QueryFacets(
                primary_intent="general",
                candidate_facets=(),
                teacher_scope=None,
                event_scope=None,
                planner_version=self.PLANNER_VERSION,
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _plan(self, query: str) -> QueryFacets:
        text = (query or "").strip()
        if not text:
            return QueryFacets(
                primary_intent="general",
                candidate_facets=(),
                teacher_scope=None,
                event_scope=None,
                planner_version=self.PLANNER_VERSION,
            )

        lower = text.lower()

        # 1. Teacher scope detection.
        teacher_scope = self._detect_teacher(lower)

        # 2. Event scope detection (crude: presence of "retreat", "session", "seminar").
        event_scope = self._detect_event_scope(lower)

        # 3. Keyword-driven primary intent.
        primary = self._detect_primary_intent(lower)

        # 4. Broad topic → candidate facets (additive; never override primary).
        candidates = self._detect_candidate_facets(lower, primary)

        return QueryFacets(
            primary_intent=primary,
            candidate_facets=candidates,
            teacher_scope=teacher_scope,
            event_scope=event_scope,
            planner_version=self.PLANNER_VERSION,
        )

    def _detect_teacher(self, lower: str) -> str | None:
        """Return canonical guru_id or None (both/unspecified).

        When both teacher names appear in the query (e.g. "Krishnaji and
        Preethaji"), returns None — both teachers are in scope.
        """
        hits = _TEACHER_PATTERN.findall(lower)
        if not hits:
            return None
        # Normalise each matched name.
        guru_ids = {_TEACHER_NAME_MAP.get(h.lower()) for h in hits}
        # Filter out None values introduced by "both"/"together"/"either".
        non_null = {g for g in guru_ids if g is not None}
        if len(non_null) > 1:
            # Multiple distinct gurus requested → no single scope.
            return None
        if len(non_null) == 1:
            return next(iter(non_null))
        # Only None values (both/either/together) → no single scope.
        return None

    def _detect_event_scope(self, lower: str) -> str | None:
        """Return a non-None scope label when the query references a specific event."""
        _EVENT_SCOPE_RE = re.compile(
            r"\b(retreat|seminar|session|workshop|ekam\s+world\s+peace\s+festival)\b",
            re.IGNORECASE,
        )
        hit = _EVENT_SCOPE_RE.search(lower)
        return hit.group(1) if hit else None

    def _detect_primary_intent(self, lower: str) -> str:
        """Return the strongest facet detected from keyword patterns.

        Scans ALL keyword matches and picks the one with the highest-priority
        facet. "distinction" phrases outrank "definition" because a query like
        "What is the difference between X and Y?" has a primary intent of
        *distinction* even though it also contains "what is".
        """
        _FACET_PRIORITY: dict[str, int] = {
            "distinction": 10,
            "practice": 8,
            "transformation": 7,
            "cause": 6,
            "definition": 5,
            "experience": 4,
            "inner_state": 3,
            "relationship": 3,
            "connection": 2,
            "attachment": 2,
            "suffering": 2,
            "compassion": 2,
            "awareness": 2,
            "presence": 2,
            "general": 0,
        }
        best_facet = "general"
        best_priority = -1
        for hit in _FACET_PATTERN.finditer(lower):
            key = hit.group(1).lower()
            facet = _FACET_KEYWORD_MAP.get(key, "general")
            priority = _FACET_PRIORITY.get(facet, 0)
            if priority > best_priority:
                best_priority = priority
                best_facet = facet
        return best_facet

    def _detect_candidate_facets(self, lower: str, primary: str) -> tuple[str, ...]:
        """Return additional candidate facets from broad topic words."""
        topic_hit = _BROAD_TOPIC_PATTERN.search(lower)
        if not topic_hit:
            return ()
        topic = topic_hit.group(1).lower()
        all_facets = _TOPIC_BROAD_MAP.get(topic, ())
        # Exclude primary intent to avoid duplication; preserve order.
        return tuple(f for f in all_facets if f != primary)


# Module-level singleton for use by the pipeline.
_DEFAULT_PLANNER: FirstPersonFacetPlanner | None = None


def get_default_planner() -> FirstPersonFacetPlanner:
    """Return the module-level singleton planner (created lazily)."""
    global _DEFAULT_PLANNER  # noqa: PLW0603
    if _DEFAULT_PLANNER is None:
        _DEFAULT_PLANNER = FirstPersonFacetPlanner()
    return _DEFAULT_PLANNER


if __name__ == "__main__":
    planner = FirstPersonFacetPlanner()

    plan = planner.plan("What is love according to Krishnaji and Preethaji?")
    assert plan.primary_intent == "definition", plan.primary_intent
    # Both teachers → no single teacher_scope
    assert plan.teacher_scope is None, plan.teacher_scope
    assert "experience" in plan.candidate_facets or "connection" in plan.candidate_facets

    plan2 = planner.plan("What did Preethaji say about suffering?")
    assert plan2.teacher_scope == "preethaji", plan2.teacher_scope

    plan3 = planner.plan("How do I meditate?")
    assert plan3.primary_intent == "practice", plan3.primary_intent

    plan4 = planner.plan("")
    assert plan4.primary_intent == "general"

    print("first_person_facet_planner self-check passed")
