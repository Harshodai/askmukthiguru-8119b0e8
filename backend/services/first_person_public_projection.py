"""Public projection for bounded first-person editorial selection metadata.

Only finite policy facts are exposed. Candidate text, source IDs, retrieval
scores, event names, exclusion reasons, and arbitrary future fields stay private.
"""

from __future__ import annotations

from typing import Any

from domain.first_person_facets import FACET_PLANNER_VERSION, KNOWN_TOPIC_FACETS
from services.first_person_set_selector import SET_SELECTOR_VERSION

_EDITORIAL_SET_STATUSES = frozenset({"supported", "partial", "conflicted", "insufficient"})
_EDITORIAL_COVERAGE_LEVELS = frozenset({"direct", "indirect", "absent"})
_ALLOWED_FACETS = KNOWN_TOPIC_FACETS | {"general"}


def public_editorial_set_metadata(value: Any) -> dict[str, Any] | None:
    """Return only bounded, non-prose editorial-set facts fit for clients."""
    if not isinstance(value, dict):
        return None
    status = value.get("status")
    if not isinstance(status, str) or status not in _EDITORIAL_SET_STATUSES:
        return None

    primary_intent = value.get("primary_intent")
    if not isinstance(primary_intent, str) or primary_intent not in _ALLOWED_FACETS:
        primary_intent = "general"
    raw_facets = value.get("candidate_facets")
    candidate_facets = (
        [facet for facet in raw_facets if isinstance(facet, str) and facet in _ALLOWED_FACETS][:14]
        if isinstance(raw_facets, list)
        else []
    )
    raw_coverage = value.get("facet_coverage")
    facet_coverage = (
        {
            facet: level
            for facet, level in list(raw_coverage.items())[:14]
            if isinstance(facet, str)
            and facet in _ALLOWED_FACETS
            and isinstance(level, str)
            and level in _EDITORIAL_COVERAGE_LEVELS
        }
        if isinstance(raw_coverage, dict)
        else {}
    )
    teacher_scope = value.get("teacher_scope")
    if not isinstance(teacher_scope, str) or teacher_scope not in {"krishnaji", "preethaji"}:
        teacher_scope = None

    def _count(name: str, maximum: int) -> int:
        raw = value.get(name, 0)
        if isinstance(raw, bool) or not isinstance(raw, int):
            return 0
        return max(0, min(maximum, raw))

    return {
        "status": status,
        "primary_intent": primary_intent,
        "candidate_facets": candidate_facets,
        "teacher_scope": teacher_scope,
        "facet_coverage": facet_coverage,
        "candidate_contexts": _count("candidate_contexts", 8),
        "selected_contexts": _count("selected_contexts", 5),
        "planner_version": FACET_PLANNER_VERSION,
        "selector_version": SET_SELECTOR_VERSION,
    }
