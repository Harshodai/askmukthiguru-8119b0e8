"""Evidence set selector for first-person editorial teaching answers.

Replaces the "score only the first three available clips per facet" approach
with a proper set-selection algorithm that:
- Requires at least one direct-evidence clip when ``require_direct=True``.
- Removes near-duplicates (high token-overlap clips from the same parent).
- Reports ``supported | partial | conflicted | insufficient`` for the set.
- Prefers distinct video IDs when score-tied.
- Enforces teacher-scope from ``QueryFacets.teacher_scope``.
- Never force-fills a facet slot with a tangential clip.

Design constraints:
- No LLM calls, no network calls, no Qdrant reads.
- Deterministic: same inputs → same selection.
- Fail-closed: on any internal exception, returns ``insufficient`` with
  zero selected clips so the pipeline can abstain honestly.
- Does not alter span text or rights/speaker decisions from upstream gates.
- All gates applied upstream (rights, speaker, boundary, safety) are
  respected; this module only ranks and selects from the already-gated pool.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

SET_SELECTOR_VERSION = "first_person_set_selector_v1"

# ---------------------------------------------------------------------------
# Near-duplicate detection threshold.
# Two clips are near-duplicates when their normalised token-overlap Jaccard
# score exceeds this value.
# ---------------------------------------------------------------------------
_NEAR_DUPLICATE_THRESHOLD = 0.80

# Minimum words for a clip to be considered content-bearing for scoring.
_MIN_WORDS = 5

# ---------------------------------------------------------------------------
# Simple stance-marker sets for conflict detection.
# A "conflicted" set contains both affirmative and negating stance markers
# for the same facet topic word — indicating genuinely contradictory positions.
# ---------------------------------------------------------------------------
_AFFIRMATIVE_MARKERS = frozenset(
    {
        "is",
        "are",
        "means",
        "represents",
        "embodies",
        "creates",
        "produces",
        "leads to",
        "results in",
        "enables",
        "allows",
        "opens",
    }
)
_NEGATING_MARKERS = frozenset(
    {
        "is not",
        "are not",
        "isn't",
        "aren't",
        "does not",
        "doesn't",
        "never",
        "nothing to do with",
        "has nothing",
        "opposite of",
        "not what",
        "not about",
    }
)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScoredSpan:
    """A candidate span with its selection score and facet assignment."""

    span_id: str
    video_id: str
    guru_id: str
    text: str
    score: float  # 0.0–1.0; higher = better for this query
    is_direct: bool  # from upstream harness decision
    facet: str  # best-matching facet from QueryFacets
    source: object  # the original SourceSpan (opaque to this module)


@dataclass(frozen=True, slots=True)
class EvidenceSetDecision:
    """Outcome of the set-selection algorithm.

    ``status`` is the authoritative set-level verdict:
    - ``supported``    → set has at least one direct clip; facets have evidence.
    - ``partial``      → only indirect / weak-match clips available; or some
                         facets are absent.
    - ``conflicted``   → selected clips appear to take contradictory positions
                         on the same facet topic.
    - ``insufficient`` → not enough eligible clips to form a meaningful set.

    ``excluded`` carries (span_id, reason) pairs for the audit trail.
    ``facet_coverage`` maps each planned facet to its coverage level.
    """

    status: Literal["supported", "partial", "conflicted", "insufficient"]
    selected: tuple[ScoredSpan, ...]
    excluded: tuple[tuple[str, str], ...]  # (span_id, reason)
    facet_coverage: dict[str, Literal["direct", "indirect", "absent"]]
    reasons: tuple[str, ...]
    selector_version: str = SET_SELECTOR_VERSION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalised_tokens(text: str) -> frozenset[str]:
    """Return a frozenset of lowercased word tokens from ``text``."""
    return frozenset(re.findall(r"\b[a-z]{3,}\b", text.lower()))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _score_facet_match(text: str, facet: str) -> float:
    """Return a rough [0.0, 1.0] score for how well ``text`` addresses ``facet``."""
    # Simple keyword overlap with facet label and synonyms.
    _FACET_SYNONYMS: dict[str, list[str]] = {
        "definition": ["is", "means", "define", "what", "essentially", "fundamentally"],
        "distinction": ["difference", "unlike", "versus", "not the same", "contrast"],
        "practice": ["how", "method", "technique", "practice", "step", "way"],
        "experience": ["feel", "experience", "sense", "notice", "aware", "moment"],
        "inner_state": ["state", "inner", "within", "being", "stillness", "peace"],
        "cause": ["because", "why", "reason", "arises", "comes from", "root"],
        "transformation": ["change", "transform", "shift", "move from", "overcome", "free"],
        "suffering": ["suffering", "pain", "hurt", "struggle", "difficulty", "stress"],
        "connection": ["connect", "oneness", "together", "unity", "relationship", "bond"],
        "attachment": ["attachment", "cling", "holding", "let go", "release", "depend"],
        "compassion": ["compassion", "kindness", "empathy", "care", "heart", "tender"],
        "awareness": ["aware", "consciousness", "conscious", "notice", "witness", "observe"],
        "presence": ["present", "here", "now", "moment", "presence", "alive"],
        "relationship": ["relationship", "partner", "spouse", "other", "together", "bond"],
        "general": [],
    }
    keywords = _FACET_SYNONYMS.get(facet, [facet])
    if not keywords:
        return 0.3  # partial score for unknown facets
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw in text_lower)
    return min(1.0, hits / max(1, len(keywords)) * 2.0)


def _best_facet(text: str, facets: tuple[str, ...]) -> tuple[str, float]:
    """Return (best_facet, score) from the candidate facet list."""
    if not facets:
        return ("general", 0.2)
    scored = [(f, _score_facet_match(text, f)) for f in facets]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0]


def _detect_stance_conflict(clips: list[ScoredSpan], topic_words: list[str]) -> bool:
    """Return True when clips appear to take contradictory positions on topic_words."""
    has_affirm = False
    has_negate = False
    for clip in clips:
        lower = clip.text.lower()
        for tw in topic_words:
            for marker in _AFFIRMATIVE_MARKERS:
                if f"{tw} {marker}" in lower or f"{marker} {tw}" in lower:
                    has_affirm = True
            for marker in _NEGATING_MARKERS:
                if marker in lower and tw in lower:
                    has_negate = True
    return has_affirm and has_negate


# ---------------------------------------------------------------------------
# Main selector
# ---------------------------------------------------------------------------


class FirstPersonSetSelector:
    """Select a coherent, de-duplicated, facet-covering evidence set.

    This module operates exclusively on the already-gated candidate pool.
    It does not re-apply rights, speaker, or safety gates — those must have
    been applied before candidates are passed in.
    """

    SELECTOR_VERSION = SET_SELECTOR_VERSION

    def select(
        self,
        query: str,
        facets: QueryFacets,  # type: ignore[name-defined]  # imported below
        candidates: Sequence[object],
        *,
        max_clips: int = 3,
        require_direct: bool = True,
    ) -> EvidenceSetDecision:
        """Return an ``EvidenceSetDecision`` for the given candidates.

        ``candidates`` must be an iterable of objects with at minimum:
        - ``.source_span_id: str``
        - ``.video_id: str``
        - ``.guru_id: str``
        - ``.text: str`` or ``.answer_text: str``
        - ``.is_direct: bool`` or absent (treated as False)
        - ``.score: float`` or absent (treated as 0.5)
        - ``.speaker_verified: bool`` (must be True; unchecked here — upstream gate)

        Fail-closed: any exception → ``insufficient``.
        """
        try:
            return self._select(query, facets, candidates, max_clips, require_direct)
        except Exception:  # noqa: BLE001
            logger.exception("[SetSelector] unexpected error; returning insufficient")
            return EvidenceSetDecision(
                status="insufficient",
                selected=(),
                excluded=(),
                facet_coverage={},
                reasons=("selector_internal_error",),
                selector_version=self.SELECTOR_VERSION,
            )

    def _select(
        self,
        query: str,
        facets: object,
        candidates: Sequence[object],
        max_clips: int,
        require_direct: bool,
    ) -> EvidenceSetDecision:
        from domain.first_person_facets import QueryFacets

        if not isinstance(facets, QueryFacets):
            raise TypeError(f"facets must be QueryFacets, got {type(facets)}")

        max_clips = max(0, int(max_clips))
        planned_facets = facets.all_facets or ("general",)
        teacher_scope = facets.teacher_scope

        # ------------------------------------------------------------------
        # Step 1: Convert candidates to ScoredSpan, applying teacher scope.
        # ------------------------------------------------------------------
        scored: list[ScoredSpan] = []
        excluded: list[tuple[str, str]] = []

        for raw in candidates:
            span_id = getattr(raw, "source_span_id", None) or getattr(raw, "span_id", "")
            video_id = getattr(raw, "video_id", "") or ""
            guru_id = getattr(raw, "guru_id", "") or ""
            text = (
                getattr(raw, "text", None)
                or getattr(raw, "answer_text", None)
                or getattr(raw, "verbatim", None)
                or ""
            )
            is_direct = bool(getattr(raw, "is_direct", False))
            base_score = float(getattr(raw, "score", 0.5))

            if not span_id or not text or len(text.split()) < _MIN_WORDS:
                excluded.append((span_id or "unknown", "too_short_or_empty"))
                continue

            # Teacher scope enforcement.
            if teacher_scope and guru_id and guru_id != teacher_scope:
                excluded.append((span_id, f"teacher_scope_mismatch:{teacher_scope}"))
                continue

            facet, facet_score = _best_facet(text, planned_facets)
            # Combine base retrieval score with facet match.
            combined_score = base_score * 0.6 + facet_score * 0.4

            scored.append(
                ScoredSpan(
                    span_id=span_id,
                    video_id=video_id,
                    guru_id=guru_id,
                    text=text,
                    score=combined_score,
                    is_direct=is_direct,
                    facet=facet,
                    source=raw,
                )
            )

        if not scored:
            return EvidenceSetDecision(
                status="insufficient",
                selected=(),
                excluded=tuple(excluded),
                facet_coverage={f: "absent" for f in planned_facets},
                reasons=("no_eligible_candidates",),
                selector_version=self.SELECTOR_VERSION,
            )

        # ------------------------------------------------------------------
        # Step 2: Sort by score descending.
        # ------------------------------------------------------------------
        scored.sort(key=lambda s: s.score, reverse=True)

        # ------------------------------------------------------------------
        # Step 3: Near-duplicate removal.
        # Keep the highest-scoring span; mark others as near_duplicate.
        # ------------------------------------------------------------------
        kept: list[ScoredSpan] = []
        token_sets: list[frozenset[str]] = []

        for span in scored:
            tokens = _normalised_tokens(span.text)
            is_dup = any(
                _jaccard(tokens, existing) >= _NEAR_DUPLICATE_THRESHOLD for existing in token_sets
            )
            if is_dup:
                excluded.append((span.span_id, "near_duplicate"))
            else:
                kept.append(span)
                token_sets.append(tokens)

        if not kept:
            return EvidenceSetDecision(
                status="insufficient",
                selected=(),
                excluded=tuple(excluded),
                facet_coverage={f: "absent" for f in planned_facets},
                reasons=("all_candidates_are_near_duplicates",),
                selector_version=self.SELECTOR_VERSION,
            )

        # ------------------------------------------------------------------
        # Step 4: Apply max_clips cap, preferring direct clips and distinct
        # video IDs when score-tied.
        # ------------------------------------------------------------------
        if max_clips == 0:
            return EvidenceSetDecision(
                status="insufficient",
                selected=(),
                excluded=tuple(excluded) + tuple((s.span_id, "max_clips_zero") for s in kept),
                facet_coverage={f: "absent" for f in planned_facets},
                reasons=("max_clips_zero",),
                selector_version=self.SELECTOR_VERSION,
            )

        # Prefer direct clips; for each video_id keep the best-scoring span.
        per_video: dict[str, ScoredSpan] = {}
        overflow: list[ScoredSpan] = []

        for span in kept:
            vid = span.video_id or "unknown"
            if vid not in per_video:
                per_video[vid] = span
            elif span.score > per_video[vid].score:
                overflow.append(per_video[vid])
                per_video[vid] = span
            else:
                overflow.append(span)

        # Merge best-per-video (sorted by score) then overflow.
        candidates_for_cap = sorted(per_video.values(), key=lambda s: s.score, reverse=True)
        candidates_for_cap += sorted(overflow, key=lambda s: s.score, reverse=True)

        # Re-sort: direct clips first, then by score.
        candidates_for_cap.sort(key=lambda s: (not s.is_direct, -s.score))

        selected = candidates_for_cap[:max_clips]
        remaining = candidates_for_cap[max_clips:]
        for s in remaining:
            excluded.append((s.span_id, "cap_exceeded"))

        # ------------------------------------------------------------------
        # Step 5: Check direct-evidence requirement.
        # ------------------------------------------------------------------
        has_direct = any(s.is_direct for s in selected)
        if require_direct and not has_direct:
            return EvidenceSetDecision(
                status="insufficient",
                selected=(),
                excluded=tuple(excluded)
                + tuple((s.span_id, "no_direct_evidence") for s in selected),
                facet_coverage={f: "absent" for f in planned_facets},
                reasons=("no_direct_evidence",),
                selector_version=self.SELECTOR_VERSION,
            )

        # ------------------------------------------------------------------
        # Step 6: Compute facet coverage.
        # ------------------------------------------------------------------
        facet_coverage: dict[str, Literal["direct", "indirect", "absent"]] = {}
        for f in planned_facets:
            best_for_facet = [s for s in selected if s.facet == f]
            if not best_for_facet:
                facet_coverage[f] = "absent"
            elif any(s.is_direct for s in best_for_facet):
                facet_coverage[f] = "direct"
            else:
                facet_coverage[f] = "indirect"

        # ------------------------------------------------------------------
        # Step 7: Conflict detection.
        # ------------------------------------------------------------------
        topic_words = [w for w in query.lower().split() if len(w) > 3][:5]
        is_conflicted = _detect_stance_conflict(list(selected), topic_words)

        # ------------------------------------------------------------------
        # Step 8: Determine set status.
        # ------------------------------------------------------------------
        n_direct = sum(1 for s in selected if s.is_direct)
        n_absent = sum(1 for v in facet_coverage.values() if v == "absent")

        if is_conflicted:
            status: Literal["supported", "partial", "conflicted", "insufficient"] = "conflicted"
            reasons: tuple[str, ...] = ("conflicting_positions_detected",)
        elif n_direct >= 1 and n_absent == 0:
            status = "supported"
            reasons = ()
        elif n_direct >= 1:
            status = "partial"
            reasons = ("some_facets_absent",) if n_absent else ()
        else:
            status = "partial"
            reasons = ("no_direct_evidence_in_selection",)

        return EvidenceSetDecision(
            status=status,
            selected=tuple(selected),
            excluded=tuple(excluded),
            facet_coverage=facet_coverage,
            reasons=reasons,
            selector_version=self.SELECTOR_VERSION,
        )


if __name__ == "__main__":
    from types import SimpleNamespace

    from domain.first_person_facets import QueryFacets

    planner_facets = QueryFacets(
        primary_intent="definition",
        candidate_facets=("experience",),
        teacher_scope=None,
        event_scope=None,
    )
    c1 = SimpleNamespace(
        source_span_id="span1",
        video_id="vid1",
        guru_id="krishnaji",
        text="Love is a state of deep connection with all of existence. It is not a feeling but a state of being.",
        is_direct=True,
        score=0.9,
    )
    c2 = SimpleNamespace(
        source_span_id="span2",
        video_id="vid2",
        guru_id="preethaji",
        text="When you experience love, there is no separation. You are complete in that moment.",
        is_direct=False,
        score=0.7,
    )

    selector = FirstPersonSetSelector()
    decision = selector.select("What is love?", planner_facets, [c1, c2], max_clips=3)
    assert decision.status in ("supported", "partial"), decision.status
    assert len(decision.selected) == 2
    print(f"first_person_set_selector self-check passed: status={decision.status}")
