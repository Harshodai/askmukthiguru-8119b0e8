"""Typed query facet model for first-person editorial set selection.

Facets are retrieval hypotheses — not required fills. The system must report
that a facet is absent rather than force-filling it with a tangential clip.

Teacher scope is explicit: if the user asks only about Preethaji, Krishnaji
clips must not be substituted. If both are requested but only one has verified
evidence, the selector must report that honestly.
"""

from __future__ import annotations

from dataclasses import dataclass

FACET_PLANNER_VERSION = "first_person_facets_v1"

# ---------------------------------------------------------------------------
# Known topic facets for the spiritual teaching domain.
# These are candidate retrieval hypotheses expanded at planning time.
# ---------------------------------------------------------------------------
KNOWN_TOPIC_FACETS: frozenset[str] = frozenset(
    {
        "definition",
        "distinction",
        "practice",
        "experience",
        "relationship",
        "inner_state",
        "cause",
        "transformation",
        "suffering",
        "connection",
        "attachment",
        "compassion",
        "awareness",
        "presence",
    }
)

# Keyword → facet hypothesis mappings (deterministic, no LLM).
_FACET_KEYWORD_MAP: dict[str, str] = {
    "what is": "definition",
    "define": "definition",
    "meaning of": "definition",
    "difference between": "distinction",
    "differ": "distinction",
    "versus": "distinction",
    "vs": "distinction",
    "compare": "distinction",
    "how to": "practice",
    "how do i": "practice",
    "how can i": "practice",
    "practice": "practice",
    "technique": "practice",
    "exercise": "practice",
    "method": "practice",
    "feel": "experience",
    "experience": "experience",
    "sense": "experience",
    "inner": "inner_state",
    "state": "inner_state",
    "relationship": "relationship",
    "relate": "relationship",
    "partner": "relationship",
    "attachment": "attachment",
    "attached": "attachment",
    "clinging": "attachment",
    "suffering": "suffering",
    "pain": "suffering",
    "hurt": "suffering",
    "compassion": "compassion",
    "kind": "compassion",
    "empathy": "compassion",
    "presence": "presence",
    "aware": "awareness",
    "consciousness": "awareness",
    "connection": "connection",
    "connect": "connection",
    "oneness": "connection",
    "cause": "cause",
    "why": "cause",
    "reason": "cause",
    "transform": "transformation",
    "change": "transformation",
    "overcome": "transformation",
}

# Guru names → canonical guru_id used in the corpus.
_TEACHER_NAME_MAP: dict[str, str] = {
    "krishnaji": "krishnaji",
    "sri krishnaji": "krishnaji",
    "preethaji": "preethaji",
    "sri preethaji": "preethaji",
    "both": None,
    "together": None,
    "either": None,
}


@dataclass(frozen=True, slots=True)
class QueryFacets:
    """Facet plan derived from a user query.

    ``primary_intent`` is the strongest detected facet (or ``"general"``).
    ``candidate_facets`` are additional hypotheses to attempt — the selector
    should report ``"absent"`` for any facet it cannot fill, never force a clip.
    ``teacher_scope`` is the canonical guru_id requested, or ``None`` (both).
    ``event_scope`` is non-None only when the query explicitly references a
    specific session, retreat, or event.
    ``planner_version`` ties this plan to the vocabulary it was built with.
    """

    primary_intent: str
    candidate_facets: tuple[str, ...]
    teacher_scope: str | None
    event_scope: str | None
    planner_version: str = FACET_PLANNER_VERSION

    @property
    def all_facets(self) -> tuple[str, ...]:
        """Primary intent plus all candidate facets, deduplicated in order."""
        seen: set[str] = set()
        result: list[str] = []
        for f in (self.primary_intent, *self.candidate_facets):
            if f and f not in seen:
                seen.add(f)
                result.append(f)
        return tuple(result)


if __name__ == "__main__":
    qf = QueryFacets(
        primary_intent="definition",
        candidate_facets=("experience", "practice"),
        teacher_scope=None,
        event_scope=None,
    )
    assert qf.all_facets == ("definition", "experience", "practice")
    assert qf.teacher_scope is None
    print("first_person_facets self-check passed")
